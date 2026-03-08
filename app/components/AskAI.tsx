import { useState, useRef, useEffect } from 'react';
import {
  View, Text, TextInput, ScrollView, Pressable, StyleSheet,
  KeyboardAvoidingView, Platform, ActivityIndicator,
} from 'react-native';
import { colors, fonts, type } from '../design/tokens';
import { askAI } from '../lib/chat-api';
import { logEvent } from '../data/logger';

interface Message {
  role: 'user' | 'assistant';
  content: string;
}

interface AskAIProps {
  context: string;
  articleId: string;
  onClose: () => void;
  initialQuestion?: string;
}

export default function AskAI({ context, articleId, onClose, initialQuestion }: AskAIProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [conversationId, setConversationId] = useState<string | undefined>();
  const scrollRef = useRef<ScrollView>(null);
  const initialSent = useRef(false);

  // Auto-send initial question if provided
  useEffect(() => {
    if (initialQuestion && !initialSent.current) {
      initialSent.current = true;
      sendQuestion(initialQuestion);
    }
  }, [initialQuestion]);

  const sendQuestion = async (question: string) => {
    setMessages(prev => [...prev, { role: 'user', content: question }]);
    setLoading(true);
    logEvent('ai_chat_send', { article_id: articleId, question_length: question.length });
    try {
      const resp = await askAI(question, context, conversationId);
      setConversationId(resp.conversation_id);
      setMessages(prev => [...prev, { role: 'assistant', content: resp.answer }]);
      logEvent('ai_chat_response', { article_id: articleId, answer_length: resp.answer.length });
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
        {/* Header */}
        <View style={styles.header}>
          <Text style={styles.headerTitle}>{'✦ Ask AI'}</Text>
          <Pressable onPress={onClose} style={styles.closeButton}>
            <Text style={styles.closeText}>Done</Text>
          </Pressable>
        </View>

        {/* Messages */}
        <ScrollView ref={scrollRef} style={styles.messageList} contentContainerStyle={styles.messageContent}>
          {messages.length === 0 && (
            <View style={styles.emptyState}>
              <Text style={styles.emptyText}>
                Ask anything about this article. The AI has the full text, summary, claims, and topics as context.
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
              <ActivityIndicator size="small" color={colors.textMuted} />
            </View>
          )}
        </ScrollView>

        {/* Input */}
        <View style={styles.inputRow}>
          <TextInput
            style={styles.input}
            value={input}
            onChangeText={setInput}
            placeholder="Ask about this article..."
            placeholderTextColor={colors.textMuted}
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
            <Text style={styles.sendButtonText}>→</Text>
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
    backgroundColor: colors.parchment,
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
    borderBottomColor: colors.rule,
  },
  headerTitle: {
    ...type.sectionHead,
    color: colors.rubric,
  },
  closeButton: {
    paddingVertical: 4,
    paddingHorizontal: 8,
  },
  closeText: {
    fontFamily: fonts.ui,
    fontSize: 14,
    color: colors.textMuted,
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
    color: colors.textSecondary,
    textAlign: 'center',
  },
  bubble: {
    paddingHorizontal: 14,
    paddingVertical: 10,
    maxWidth: '85%',
  },
  userBubble: {
    alignSelf: 'flex-end',
    backgroundColor: colors.ink,
    borderRadius: 14,
    borderBottomRightRadius: 4,
  },
  aiBubble: {
    alignSelf: 'flex-start',
    backgroundColor: colors.parchmentDark,
    borderRadius: 14,
    borderBottomLeftRadius: 4,
  },
  bubbleText: {
    fontFamily: fonts.reading,
    fontSize: 14,
    lineHeight: 21,
    color: colors.textBody,
  },
  userBubbleText: {
    color: colors.parchment,
  },
  inputRow: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.rule,
    gap: 8,
  },
  input: {
    flex: 1,
    fontFamily: fonts.reading,
    fontSize: 15,
    color: colors.textBody,
    backgroundColor: colors.parchmentDark,
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: 20,
    maxHeight: 100,
  },
  sendButton: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: colors.ink,
    justifyContent: 'center',
    alignItems: 'center',
  },
  sendButtonDisabled: {
    backgroundColor: colors.rule,
  },
  sendButtonText: {
    fontFamily: fonts.display,
    fontSize: 18,
    color: colors.parchment,
  },
});
