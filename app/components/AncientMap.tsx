/**
 * AncientMap — Interactive Mediterranean map for historical entities.
 *
 * Renders a Leaflet map inside a WebView (native) or iframe (web) with
 * parchment-filtered terrain tiles, knowledge-state markers, filters,
 * time slider, and entity selection.
 *
 * Usage:
 *
 *   // Full map screen with all controls
 *   <AncientMap entities={entities} filters={DOMAIN_FILTERS} />
 *
 *   // Mini map in entity intro card, centered on one place
 *   <AncientMap
 *     entities={[syracuse]}
 *     center={[37.0755, 15.2866]}
 *     zoom={9}
 *     showControls={false}
 *     showTimeline={false}
 *     showFilters={false}
 *     showEntitySheet={false}
 *     style={{ height: 200 }}
 *   />
 *
 *   // Map with callback for native EntitySheet
 *   <AncientMap
 *     entities={entities}
 *     showEntitySheet={false}
 *     onEntitySelect={(entity) => setSelectedEntityId(entity.entityId)}
 *   />
 */

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Platform, StyleSheet, View, ViewStyle } from 'react-native';
import { WebView, WebViewMessageEvent } from 'react-native-webview';
import { EntityDetails } from '../data/types';
import { colors } from '../design/tokens';
import { getMapHtmlUrl } from '../lib/server-urls';

// ── Types ─────────────────────────────────────────────────────────────────────

/** Filter definition passed to the map. Filters by entity field value or explicit ID list. */
export interface MapFilter {
  id: string;
  label: string;
  /** Match by field equality: { field: 'region', value: 'greek_sicily' } */
  field?: string;
  value?: string;
  /** Or match by explicit entity ID list */
  entityIds?: string[];
}

/** Route/connection line between two entities. */
export interface MapRoute {
  id: string;
  from: string;
  to: string;
  label?: string;
  waypoints: [number, number][];
}

/** Event fired when an entity is selected on the map. */
export interface MapSelectEvent {
  entityId: string;
  name: string;
  entityType: string;
  knowledge: string;
}

/** Event fired when user taps an action button on the entity sheet. */
export interface MapActionEvent {
  entityId: string;
  action: 'unknown' | 'interested' | 'got_it';
}

interface Props {
  /** Entity data to display on the map. Must have latitude/longitude. */
  entities: EntityDetails[];
  /** Optional filter pill definitions. */
  filters?: MapFilter[];
  /** Optional route/connection lines. */
  routes?: MapRoute[];
  /** Initial map center [lat, lon]. Default: Mediterranean center. */
  center?: [number, number];
  /** Initial zoom level. Default: 6. */
  zoom?: number;
  /** Initially selected entity ID. */
  selectedEntityId?: string;
  /** Entity IDs to highlight (e.g., from current review session). */
  highlightEntityIds?: string[];
  /** Initial tile layer: 'terrain' | 'clean' | 'satellite'. Default: 'terrain'. */
  tileLayer?: string;
  /** Show filter pills. Default: true (if filters provided). */
  showFilters?: boolean;
  /** Show time slider. Default: true. */
  showTimeline?: boolean;
  /** Show layer/label/route controls. Default: true. */
  showControls?: boolean;
  /** Show legend. Default: true. */
  showLegend?: boolean;
  /** Show in-HTML entity sheet on tap. Set false to handle via onEntitySelect. Default: true. */
  showEntitySheet?: boolean;
  /** Called when an entity marker is tapped. */
  onEntitySelect?: (event: MapSelectEvent | null) => void;
  /** Called when user taps an action button on the entity sheet. */
  onEntityAction?: (event: MapActionEvent) => void;
  /** Called when map is ready. */
  onReady?: () => void;
  /** Container style override. */
  style?: ViewStyle;
}

/** Imperative handle exposed via ref. */
export interface AncientMapRef {
  focusEntity: (entityId: string) => void;
  selectEntity: (entityId: string | null) => void;
  highlightEntities: (entityIds: string[]) => void;
  updateKnowledge: (entityId: string, state: string) => void;
  setFilter: (filterId: string | null) => void;
  setTileLayer: (layerId: string) => void;
  fitAll: () => void;
}

// ── Map HTML source ───────────────────────────────────────────────────────────

const MAP_HTML_URI = getMapHtmlUrl();

// ── Component ─────────────────────────────────────────────────────────────────

const AncientMap = React.forwardRef<AncientMapRef, Props>(function AncientMap(props, ref) {
  const {
    entities, filters, routes, center, zoom, selectedEntityId,
    highlightEntityIds, tileLayer,
    showFilters, showTimeline = true, showControls = true,
    showLegend = true, showEntitySheet = true,
    onEntitySelect, onEntityAction, onReady, style,
  } = props;

  const webViewRef = useRef<WebView>(null);
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [ready, setReady] = useState(false);

  // ── Build init config ───────────────────────────────────────────────────────

  const buildConfig = useCallback(() => ({
    entities: entities.map(e => ({
      entity_id: e.entity_id,
      name: e.name,
      entity_type: e.entity_type,
      modern_name: e.modern_name,
      latitude: e.latitude,
      longitude: e.longitude,
      description: e.description,
      dates: e.dates,
      date_start: e.date_start,
      date_end: e.date_end,
      nexus_score: e.nexus_score,
      curriculum_links: e.curriculum_links,
      aliases: e.aliases,
      // Custom fields for filtering
      ...(e as any).region ? { region: (e as any).region } : {},
    })),
    filters,
    routes,
    center,
    zoom,
    selectedEntityId,
    highlightEntityIds,
    tileLayer,
    showFilters,
    showTimeline,
    showControls,
    showLegend,
    showEntitySheet,
  }), [entities, filters, routes, center, zoom, selectedEntityId,
    highlightEntityIds, tileLayer, showFilters, showTimeline,
    showControls, showLegend, showEntitySheet]);

  // ── Send command to map ─────────────────────────────────────────────────────

  const sendCommand = useCallback((method: string, ...args: any[]) => {
    const msg = JSON.stringify({ type: 'command', method, args });
    if (Platform.OS === 'web') {
      iframeRef.current?.contentWindow?.postMessage(
        { type: 'command', method, args }, '*'
      );
    } else {
      webViewRef.current?.injectJavaScript(
        `mapInstance?.${method}(${args.map(a => JSON.stringify(a)).join(',')});true;`
      );
    }
  }, []);

  // ── Expose ref methods ──────────────────────────────────────────────────────

  React.useImperativeHandle(ref, () => ({
    focusEntity: (id) => sendCommand('focusEntity', id),
    selectEntity: (id) => sendCommand('selectEntity', id),
    highlightEntities: (ids) => sendCommand('highlightEntities', ids),
    updateKnowledge: (id, state) => sendCommand('updateKnowledge', id, state),
    setFilter: (id) => sendCommand('setFilter', id),
    setTileLayer: (id) => sendCommand('setTileLayer', id),
    fitAll: () => sendCommand('fitAll'),
  }), [sendCommand]);

  // ── Handle messages from map ────────────────────────────────────────────────

  const handleMessage = useCallback((event: { type: string; data: any }) => {
    switch (event.type) {
      case 'ready':
        setReady(true);
        onReady?.();
        break;
      case 'select':
        onEntitySelect?.(event.data);
        break;
      case 'action':
        onEntityAction?.(event.data);
        break;
    }
  }, [onEntitySelect, onEntityAction, onReady]);

  // ── Native WebView message handler ──────────────────────────────────────────

  const onWebViewMessage = useCallback((e: WebViewMessageEvent) => {
    try {
      const msg = JSON.parse(e.nativeEvent.data);
      handleMessage(msg);
    } catch {}
  }, [handleMessage]);

  // ── Web iframe message handler ──────────────────────────────────────────────

  useEffect(() => {
    if (Platform.OS !== 'web') return;
    const handler = (e: MessageEvent) => {
      if (e.data?.source === 'ancient-map') {
        handleMessage(e.data);
      }
    };
    window.addEventListener('message', handler);
    return () => window.removeEventListener('message', handler);
  }, [handleMessage]);

  // ── Send init when iframe loads (web) ───────────────────────────────────────

  const onIframeLoad = useCallback(() => {
    iframeRef.current?.contentWindow?.postMessage(
      { type: 'init', config: buildConfig() }, '*'
    );
  }, [buildConfig]);

  // ── Injected JS for WebView init (native) ──────────────────────────────────

  const injectedJS = `
    window.addEventListener('load', function() {
      initMap(${JSON.stringify(buildConfig())});
    });
    true;
  `;

  // ── Render ──────────────────────────────────────────────────────────────────

  if (Platform.OS === 'web') {
    return (
      <View style={[styles.container, style]}>
        <iframe
          ref={iframeRef as any}
          src={MAP_HTML_URI}
          onLoad={onIframeLoad}
          style={{
            width: '100%',
            height: '100%',
            border: 'none',
            backgroundColor: colors.parchment,
          }}
          allow="geolocation"
        />
      </View>
    );
  }

  return (
    <View style={[styles.container, style]}>
      <WebView
        ref={webViewRef}
        source={{ uri: MAP_HTML_URI }}
        injectedJavaScript={injectedJS}
        onMessage={onWebViewMessage}
        javaScriptEnabled
        domStorageEnabled
        startInLoadingState
        style={styles.webview}
        containerStyle={styles.webviewContainer}
        scrollEnabled={false}
        bounces={false}
        overScrollMode="never"
        showsHorizontalScrollIndicator={false}
        showsVerticalScrollIndicator={false}
        allowsInlineMediaPlayback
        mediaPlaybackRequiresUserAction={false}
      />
    </View>
  );
});

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.parchment,
    overflow: 'hidden',
  },
  webview: {
    flex: 1,
    backgroundColor: 'transparent',
  },
  webviewContainer: {
    flex: 1,
  },
});

export default AncientMap;
