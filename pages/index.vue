<template>
    <div class="chat-page d-flex flex-column fill-height">
        <!-- Welcome state (no messages) -->
        <div
            v-if="!hasMessages"
            class="welcome-state d-flex flex-column align-center justify-center flex-grow-1"
        >
            <div class="welcome-content">
                <div class="welcome-header text-center mb-8">
                    <div class="ada-avatar-large mb-4">
                        <v-icon size="48" color="primary">mdi-atom-variant</v-icon>
                    </div>
                    <h1 class="welcome-title">Ada</h1>
                    <p class="welcome-subtitle">
                        Research assistant for the Lovelace Knowledge Graph
                    </p>
                </div>

                <div class="starters-grid">
                    <button
                        v-for="starter in starters"
                        :key="starter.text"
                        class="starter-card"
                        :disabled="loading || !agentReady"
                        @click="sendStarter(starter.text)"
                    >
                        <v-icon size="20" class="starter-icon" :color="starter.color">
                            {{ starter.icon }}
                        </v-icon>
                        <span class="starter-text">{{ starter.text }}</span>
                    </button>
                </div>

                <p
                    v-if="!agentReady"
                    class="text-center mt-6 text-caption"
                    style="color: var(--lv-silver)"
                >
                    <v-icon size="14" class="mr-1">mdi-information-outline</v-icon>
                    Connecting to agent...
                    <span v-if="agentError" class="text-error">{{ agentError }}</span>
                </p>
            </div>
        </div>

        <!-- Messages area -->
        <div v-else ref="messagesContainer" class="messages-area flex-grow-1 overflow-y-auto">
            <div class="messages-inner">
                <ChatMessage
                    v-for="msg in messages"
                    :key="msg.id"
                    :message="msg"
                    class="message-row"
                />
            </div>
        </div>

        <!-- Input area -->
        <div class="input-area flex-shrink-0">
            <div class="input-inner">
                <div class="d-flex align-end ga-2">
                    <v-textarea
                        v-model="inputText"
                        placeholder="Ask Ada about companies, people, relationships, events..."
                        variant="outlined"
                        density="comfortable"
                        rows="1"
                        max-rows="6"
                        auto-grow
                        hide-details
                        :disabled="loading || !agentReady"
                        class="chat-input flex-grow-1"
                        @keydown.enter.exact.prevent="handleSend"
                    />
                    <v-btn
                        icon
                        color="primary"
                        size="large"
                        :loading="loading"
                        :disabled="!inputText.trim() || !agentReady"
                        class="send-btn mb-1"
                        @click="handleSend"
                    >
                        <v-icon>mdi-send</v-icon>
                    </v-btn>
                </div>
                <div class="input-hints d-flex align-center justify-space-between mt-1">
                    <span class="text-caption" style="color: var(--lv-silver)">
                        Press Enter to send
                    </span>
                    <v-btn
                        v-if="hasMessages"
                        variant="text"
                        size="x-small"
                        color="error"
                        prepend-icon="mdi-delete-outline"
                        @click="clearChat"
                    >
                        Clear
                    </v-btn>
                </div>
            </div>
        </div>
    </div>
</template>

<script setup lang="ts">
    import { useAgentChat } from '~/composables/useAgentChat';
    import { useTenantConfig } from '~/composables/useTenantConfig';

    const { messages, loading, hasMessages, sendMessage, selectAgent, clearChat } = useAgentChat();
    const { config, fetchConfig } = useTenantConfig();

    const inputText = ref('');
    const messagesContainer = ref<HTMLElement | null>(null);
    const agentReady = ref(false);
    const agentError = ref<string | null>(null);

    const starters = [
        {
            icon: 'mdi-domain',
            text: 'Tell me about JPMorgan Chase',
            color: 'primary',
        },
        {
            icon: 'mdi-account-group',
            text: 'Who are the board members of Apple?',
            color: 'secondary',
        },
        {
            icon: 'mdi-shield-alert',
            text: 'What sanctions are associated with Russia?',
            color: 'warning',
        },
        {
            icon: 'mdi-chart-timeline-variant',
            text: 'What are the recent events for Tesla?',
            color: 'info',
        },
        {
            icon: 'mdi-sitemap',
            text: "What's the corporate structure of Berkshire Hathaway?",
            color: 'primary',
        },
        {
            icon: 'mdi-trending-up',
            text: 'What is the market sentiment for Microsoft?',
            color: 'info',
        },
    ];

    async function handleSend() {
        const text = inputText.value.trim();
        if (!text || loading.value || !agentReady.value) return;
        inputText.value = '';
        await sendMessage(text);
        scrollToBottom();
    }

    function sendStarter(text: string) {
        inputText.value = text;
        handleSend();
    }

    function scrollToBottom() {
        nextTick(() => {
            if (messagesContainer.value) {
                messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight;
            }
        });
    }

    watch(messages, () => scrollToBottom(), { deep: true });

    onMounted(async () => {
        try {
            const tenantConfig = await fetchConfig();
            const agents = tenantConfig?.agents ?? [];
            const adaAgent = agents.find(
                (a) => a.name === 'ada' || a.display_name?.toLowerCase().includes('ada')
            );

            if (adaAgent?.engine_id) {
                selectAgent(adaAgent.engine_id);
                agentReady.value = true;
            } else if (agents.length > 0) {
                selectAgent(agents[0].engine_id);
                agentReady.value = true;
            } else {
                agentError.value = 'No agents deployed yet. Deploy the Ada agent first.';
            }
        } catch (e: any) {
            agentError.value = e.message || 'Failed to connect to agent service';
        }
    });
</script>

<style scoped>
    .chat-page {
        background: var(--lv-black);
    }

    /* Welcome state */
    .welcome-state {
        padding: 24px;
    }

    .welcome-content {
        max-width: 680px;
        width: 100%;
    }

    .ada-avatar-large {
        width: 80px;
        height: 80px;
        border-radius: 50%;
        background: rgba(63, 234, 0, 0.08);
        border: 1px solid rgba(63, 234, 0, 0.2);
        display: flex;
        align-items: center;
        justify-content: center;
        margin: 0 auto;
    }

    .welcome-title {
        font-family: var(--font-headline);
        font-weight: 400;
        font-size: 2.5rem;
        letter-spacing: 0.04em;
        color: var(--lv-white);
    }

    .welcome-subtitle {
        color: var(--lv-silver);
        font-size: 1rem;
        margin-top: 4px;
    }

    .starters-grid {
        display: grid;
        grid-template-columns: repeat(2, 1fr);
        gap: 10px;
    }

    @media (max-width: 600px) {
        .starters-grid {
            grid-template-columns: 1fr;
        }
    }

    .starter-card {
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 14px 16px;
        background: var(--lv-surface);
        border: 1px solid rgba(255, 255, 255, 0.06);
        border-radius: 12px;
        cursor: pointer;
        transition: all 0.15s ease;
        text-align: left;
        color: rgba(255, 255, 255, 0.8);
        font-size: 0.875rem;
        line-height: 1.4;
    }

    .starter-card:hover:not(:disabled) {
        background: var(--lv-surface-light);
        border-color: rgba(63, 234, 0, 0.2);
    }

    .starter-card:disabled {
        opacity: 0.4;
        cursor: not-allowed;
    }

    .starter-icon {
        flex-shrink: 0;
    }

    .starter-text {
        flex: 1;
    }

    /* Messages area */
    .messages-area {
        padding: 16px 0;
    }

    .messages-inner {
        max-width: 820px;
        margin: 0 auto;
        padding: 0 24px;
    }

    .message-row {
        margin-bottom: 4px;
    }

    /* Input area */
    .input-area {
        border-top: 1px solid rgba(255, 255, 255, 0.06);
        padding: 12px 24px 16px;
        background: var(--lv-black);
    }

    .input-inner {
        max-width: 820px;
        margin: 0 auto;
    }

    .chat-input :deep(.v-field) {
        border-radius: 16px;
        background: var(--lv-surface);
    }

    .chat-input :deep(.v-field__outline) {
        border-color: rgba(255, 255, 255, 0.08);
    }

    .chat-input :deep(.v-field--focused .v-field__outline) {
        border-color: rgba(63, 234, 0, 0.4);
    }

    .send-btn {
        border-radius: 16px;
    }

    .input-hints {
        padding: 0 4px;
    }
</style>
