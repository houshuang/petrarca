import { useState, useRef, useEffect } from 'react';
import {
  View, Text, TextInput, ScrollView, Pressable, StyleSheet,
  KeyboardAvoidingView, Platform, ActivityIndicator,
} from 'react-native';
import { fonts } from '../design/tokens';
import { askAI } from '../lib/chat-api';
import { logEvent } from '../data/logger';
import type { TopicSynthesis } from '../data/types';

const fc = {
  bg: '#f5f1e8',
  ink: '#2e2924',
  accent: '#8b2500',
  body: '#3a3632',
  secondary: '#6e675e',
  muted: '#a69e90',
  line: '#ddd8cc',
  surface: '#edeade',
};

interface Message {
  role: 'user' | 'assistant';
  content: string;
}

interface SynthesisChatProps {
  synthesis: TopicSynthesis;
  onClose: () => void;
  initialQuestion?: string;
}

function buildSynthesisContext(synthesis: TopicSynthesis): string {
  const parts = [
    `Synthesis: ${synthesis.label}`,
    `Articles: ${synthesis.article_ids.length}`,
    `Claims covered: ${synthesis.total_claims_covered}/${synthesis.total_claims_in_cluster}`,
  ];

  if (synthesis.tensions.length > 0) {
    parts.push('\nTensions:');
    for (const t of synthesis.tensions) {
      if (typeof t === 'string') {
        parts.push(`- ${t}`);
      } else {
        parts.push(`- ${(t as any).label}: ${(t as any).description}`);
      }
    }
  }

  parts.push('\nSource articles:');
  for (const aid of synthesis.article_ids) {
    const cov = synthesis.article_coverage[aid];
    parts.push(`- ${aid} (${Math.round((cov || 0) * 100)}% covered)`);
  }

  const md = synthesis.synthesis_markdown;
  parts.push(`\nSynthesis text:\n${md.slice(0, 6000)}`);

  return parts.join('\n');
}

export default function SynthesisChat({ synthesis, onClose, initialQuestion }: SynthesisChatProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [conversationId, setConversationId] = useState<string | undefined>();
  const scrollRef = useRef<ScrollView>(null);
  const initialSent = useRef(false);
  const context = useRef(buildSynthesisContext(synthesis));

  useEffect(() => {
    if (initialQuestion && !initialSent.current) {
      initialSent.current = true;
      sendQuestion(initialQuestion);
    }
  }, [initialQuestion]);

  const sendQuestion = async (question: string) => {
    setMessages(prev => [...prev, { role: 'user', content: question }]);
    setLoading(true);
    logEvent('synthesis_chat_send', { cluster_id: synthesis.cluster_id, question_length: question.length });
    try {
      const resp = await askAI(question, context.current, conversationId);
      setConversationId(resp.conversation_id);
      setMessages(prev => [...prev, { role: 'assistant', content: resp.answer }]);
      logEvent('synthesis_chat_response', { cluster_id: synthesis.cluster_id, answer_length: resp.answer.length });
    } catch (e) {
      setMessages(prev => [...prev, { role: 'assistant', content: `Error: ${e}` }]);
    } finally {
      setLoading(false);
    }
  };

  const handleSend = async () => {
    const question = input.trim();
    if (!question || loading) return;
    setInput('');
    await sendQuestion(question);
  };

  useEffect(() => {
    if (messages.length > 0) {
      setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 100);
    }
  }, [messages.length]);

  return (
    <KeyboardAvoidingView
      style={styles.overlay}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <Pressable style={styles.backdrop} onPress={onClose} />
      <View style={styles.sheet}>
        <View style={styles.header}>
          <Text style={styles.headerTitle}>{'✦ Ask about this synthesis'}</Text>
          <Pressable onPress={onClose} style={styles.closeButton}>
            <Text style={styles.closeText}>Done</Text>
          </Pressable>
        </View>

        <ScrollView ref={scrollRef} style={styles.messageList} contentContainerStyle={styles.messageContent}>
          {messages.length === 0 && (
            <View style={styles.emptyState}>
              <Text style={styles.emptyText}>
                Ask anything about this synthesis. The AI has the full synthesis text, source articles, tensions, and claims as context.
              </Text>
            </View>
          )}
          {messages.map((msg, i) => (
            <View key={i} style={[styles.bubble, msg.role === 'user' ? styles.userBubble : styles.aiBubble]}>
              <Text style={[styles.bubbleText, msg.role === 'user' && styles.userBubbleText]}>
                {msg.content}
              </Text>
            </View>
          ))}
          {loading && (
            <View style={[styles.bubble, styles.aiBubble]}>
              <ActivityIndicator size="small" color={fc.muted} />
            </View>
          )}
        </ScrollView>

        <View style={styles.inputRow}>
          <TextInput
            style={styles.input}
            value={input}
            onChangeText={setInput}
            placeholder="Ask about this synthesis..."
            placeholderTextColor={fc.muted}
            multiline
            maxLength={2000}
            onSubmitEditing={handleSend}
            blurOnSubmit={false}
            returnKeyType="send"
          />
          <Pressable
            onPress={handleSend}
            style={[styles.sendButton, (!input.trim() || loading) && styles.sendButtonDisabled]}
            disabled={!input.trim() || loading}
          >
            <Text style={styles.sendButtonText}>{'\u2192'}</Text>
          </Pressable>
        </View>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  overlay: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    justifyContent: 'flex-end',
  },
  backdrop: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: 'rgba(0,0,0,0.3)',
  },
  sheet: {
    backgroundColor: fc.bg,
    borderTopLeftRadius: 16,
    borderTopRightRadius: 16,
    maxHeight: '80%',
    minHeight: 300,
    ...(Platform.OS === 'web' ? {
      boxShadow: '0 -4px 16px rgba(0,0,0,0.1)',
    } : {
      shadowColor: '#000',
      shadowOffset: { width: 0, height: -4 },
      shadowOpacity: 0.1,
      shadowRadius: 16,
      elevation: 8,
    }),
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingVertical: 14,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: fc.line,
  },
  headerTitle: {
    fontFamily: fonts.reading,
    fontSize: 14,
    color: fc.accent,
    letterSpacing: 0.3,
  },
  closeButton: {
    paddingVertical: 4,
    paddingHorizontal: 8,
  },
  closeText: {
    fontFamily: fonts.ui,
    fontSize: 14,
    color: fc.muted,
  },
  messageList: {
    flex: 1,
  },
  messageContent: {
    padding: 16,
    gap: 10,
  },
  emptyState: {
    paddingVertical: 20,
    paddingHorizontal: 8,
  },
  emptyText: {
    fontFamily: fonts.reading,
    fontSize: 14,
    lineHeight: 21,
    color: fc.secondary,
    textAlign: 'center',
  },
  bubble: {
    paddingHorizontal: 14,
    paddingVertical: 10,
    maxWidth: '85%',
  },
  userBubble: {
    alignSelf: 'flex-end',
    backgroundColor: fc.ink,
    borderRadius: 14,
    borderBottomRightRadius: 4,
  },
  aiBubble: {
    alignSelf: 'flex-start',
    backgroundColor: fc.surface,
    borderRadius: 14,
    borderBottomLeftRadius: 4,
  },
  bubbleText: {
    fontFamily: fonts.reading,
    fontSize: 14,
    lineHeight: 21,
    color: fc.body,
  },
  userBubbleText: {
    color: fc.bg,
  },
  inputRow: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: fc.line,
    gap: 8,
  },
  input: {
    flex: 1,
    fontFamily: fonts.reading,
    fontSize: 15,
    color: fc.body,
    backgroundColor: fc.surface,
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: 20,
    maxHeight: 100,
  },
  sendButton: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: fc.ink,
    justifyContent: 'center',
    alignItems: 'center',
  },
  sendButtonDisabled: {
    backgroundColor: fc.line,
  },
  sendButtonText: {
    fontFamily: fonts.displaySemiBold,
    fontSize: 18,
    color: fc.bg,
  },
});
