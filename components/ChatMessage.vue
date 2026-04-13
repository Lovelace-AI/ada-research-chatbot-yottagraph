<template>
    <div class="d-flex mb-4" :class="isUser ? 'justify-end' : 'justify-start'">
        <div
            class="chat-bubble pa-3 rounded-lg"
            :class="[isUser ? 'user-bubble' : 'agent-bubble', message.error ? 'error-bubble' : '']"
            :style="{ maxWidth: isUser ? '75%' : '100%' }"
        >
            <div v-if="!isUser" class="d-flex align-center mb-1">
                <v-icon size="16" class="mr-1" :color="message.error ? 'error' : 'primary'">
                    {{ message.error ? 'mdi-alert-circle' : 'mdi-atom-variant' }}
                </v-icon>
                <span class="text-caption text-medium-emphasis">Ada</span>
            </div>

            <div v-if="message.streaming && !message.text" class="typing-indicator">
                <span /><span /><span />
            </div>
            <div v-else-if="isUser" class="text-body-2 bubble-text" style="white-space: pre-wrap">
                {{ message.text }}
            </div>
            <div v-else class="markdown-body text-body-2" v-html="renderedMarkdown" />
            <span v-if="message.streaming && message.text" class="streaming-cursor" />

            <div class="text-caption text-medium-emphasis mt-1" style="opacity: 0.6">
                {{ formatTime(message.timestamp) }}
            </div>
        </div>
    </div>
</template>

<script setup lang="ts">
    import { marked } from 'marked';
    import type { ChatMessage } from '~/composables/useAgentChat';

    const props = defineProps<{ message: ChatMessage }>();
    const isUser = computed(() => props.message.role === 'user');

    marked.setOptions({
        breaks: true,
        gfm: true,
    });

    const renderedMarkdown = computed(() => {
        if (!props.message.text) return '';
        try {
            return marked.parse(props.message.text) as string;
        } catch {
            return props.message.text;
        }
    });

    function formatTime(ts: number): string {
        return new Date(ts).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
    }
</script>

<style scoped>
    .user-bubble {
        background: rgba(63, 234, 0, 0.1);
        border: 1px solid rgba(63, 234, 0, 0.2);
        white-space: pre-wrap;
        word-break: break-word;
    }

    .agent-bubble {
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid rgba(255, 255, 255, 0.06);
        word-break: break-word;
    }

    .error-bubble {
        background: rgba(239, 68, 68, 0.1);
        border: 1px solid rgba(239, 68, 68, 0.25);
    }

    .bubble-text {
        color: rgba(255, 255, 255, 0.87);
    }

    /* Markdown content styling */
    .markdown-body :deep(h1) {
        font-family: var(--font-headline);
        font-size: 1.3rem;
        font-weight: 400;
        margin: 12px 0 8px;
        color: var(--lv-white);
    }

    .markdown-body :deep(h2) {
        font-family: var(--font-headline);
        font-size: 1.1rem;
        font-weight: 400;
        margin: 10px 0 6px;
        color: var(--lv-white);
    }

    .markdown-body :deep(h3) {
        font-family: var(--font-headline);
        font-size: 0.95rem;
        font-weight: 500;
        margin: 8px 0 4px;
        color: rgba(255, 255, 255, 0.9);
    }

    .markdown-body :deep(p) {
        margin: 0 0 8px;
        line-height: 1.6;
        color: rgba(255, 255, 255, 0.87);
    }

    .markdown-body :deep(p:last-child) {
        margin-bottom: 0;
    }

    .markdown-body :deep(ul),
    .markdown-body :deep(ol) {
        margin: 4px 0 8px;
        padding-left: 20px;
    }

    .markdown-body :deep(li) {
        margin: 2px 0;
        line-height: 1.5;
        color: rgba(255, 255, 255, 0.87);
    }

    .markdown-body :deep(strong) {
        color: var(--lv-white);
        font-weight: 600;
    }

    .markdown-body :deep(code) {
        font-family: var(--font-mono);
        font-size: 0.85em;
        background: rgba(255, 255, 255, 0.06);
        padding: 1px 5px;
        border-radius: 4px;
        color: var(--lv-green);
    }

    .markdown-body :deep(pre) {
        background: rgba(0, 0, 0, 0.4);
        border: 1px solid rgba(255, 255, 255, 0.06);
        border-radius: 8px;
        padding: 12px;
        margin: 8px 0;
        overflow-x: auto;
    }

    .markdown-body :deep(pre code) {
        background: none;
        padding: 0;
        color: rgba(255, 255, 255, 0.8);
    }

    .markdown-body :deep(table) {
        width: 100%;
        border-collapse: collapse;
        margin: 8px 0;
        font-size: 0.85rem;
    }

    .markdown-body :deep(th) {
        text-align: left;
        padding: 6px 10px;
        border-bottom: 1px solid rgba(255, 255, 255, 0.15);
        color: var(--lv-white);
        font-weight: 600;
        font-family: var(--font-mono);
        font-size: 0.8rem;
        text-transform: uppercase;
        letter-spacing: 0.03em;
    }

    .markdown-body :deep(td) {
        padding: 5px 10px;
        border-bottom: 1px solid rgba(255, 255, 255, 0.04);
        color: rgba(255, 255, 255, 0.8);
    }

    .markdown-body :deep(tr:hover td) {
        background: rgba(255, 255, 255, 0.02);
    }

    .markdown-body :deep(blockquote) {
        border-left: 3px solid var(--lv-green);
        padding-left: 12px;
        margin: 8px 0;
        color: rgba(255, 255, 255, 0.7);
    }

    .markdown-body :deep(hr) {
        border: none;
        border-top: 1px solid rgba(255, 255, 255, 0.08);
        margin: 12px 0;
    }

    .markdown-body :deep(a) {
        color: var(--lv-blue-light, #2e5dff);
        text-decoration: none;
    }

    .markdown-body :deep(a:hover) {
        text-decoration: underline;
    }

    .streaming-cursor {
        display: inline-block;
        width: 2px;
        height: 1em;
        background: var(--lv-green);
        margin-left: 1px;
        vertical-align: text-bottom;
        animation: cursor-blink 0.8s steps(2) infinite;
    }

    @keyframes cursor-blink {
        0% {
            opacity: 1;
        }
        100% {
            opacity: 0;
        }
    }

    .typing-indicator {
        display: flex;
        gap: 4px;
        padding: 4px 0;
    }

    .typing-indicator span {
        width: 6px;
        height: 6px;
        border-radius: 50%;
        background: rgba(63, 234, 0, 0.5);
        animation: typing-bounce 1.2s ease-in-out infinite;
    }

    .typing-indicator span:nth-child(2) {
        animation-delay: 0.15s;
    }

    .typing-indicator span:nth-child(3) {
        animation-delay: 0.3s;
    }

    @keyframes typing-bounce {
        0%,
        60%,
        100% {
            transform: translateY(0);
            opacity: 0.4;
        }
        30% {
            transform: translateY(-4px);
            opacity: 1;
        }
    }
</style>
