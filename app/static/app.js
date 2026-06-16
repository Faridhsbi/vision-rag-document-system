document.addEventListener('DOMContentLoaded', () => {
    // API endpoint base URL (empty string means same origin, which works perfectly for monolithic apps)
    const API_BASE = '';

    // State
    let activeDocumentId = '';
    let currentSources = []; // Store sources for the current session query results

    // DOM Elements
    const connectionBadge = document.getElementById('connection-badge');
    const connectionStatus = document.getElementById('connection-status');
    const docSelect = document.getElementById('doc-select');
    const documentsList = document.getElementById('documents-list');
    const refreshDocsBtn = document.getElementById('refresh-docs');
    
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');
    const uploadForm = document.getElementById('upload-form');
    const uploadProgressContainer = document.getElementById('upload-progress-container');
    const uploadFilename = document.getElementById('upload-filename');
    const uploadPercentage = document.getElementById('upload-percentage');
    const uploadProgressBar = document.getElementById('upload-progress-bar');
    const uploadStatusMessage = document.getElementById('upload-status-message');

    const chatForm = document.getElementById('chat-form');
    const chatInput = document.getElementById('chat-input');
    const chatSubmit = document.getElementById('chat-submit');
    const chatMessages = document.getElementById('chat-messages');
    const chatAlert = document.getElementById('chat-alert');
    const clearChatBtn = document.getElementById('clear-chat');

    const sourceModal = document.getElementById('source-modal');
    const closeModalBtn = document.getElementById('close-modal');
    const modalBackdrop = sourceModal.querySelector('.modal-backdrop');
    const modalSourceBadge = document.getElementById('modal-source-badge');
    const modalSourceTitle = document.getElementById('modal-source-title');
    const modalPageNum = document.getElementById('modal-page-num');
    const modalScore = document.getElementById('modal-score');
    const modalChunkId = document.getElementById('modal-chunk-id');
    const modalExcerptText = document.getElementById('modal-excerpt-text');

    // Message History Source Store
    let messageSourcesStore = {}; // msgId -> list of sources

    // ==========================================================================
    // 1. Connection & Health Check
    // ==========================================================================
    async function checkHealth() {
        try {
            const response = await fetch(`${API_BASE}/health`);
            if (response.ok) {
                const data = await response.json();
                connectionBadge.className = 'status-badge status-ok';
                connectionStatus.textContent = `Online: v${data.version || '0.1.0'}`;
                return true;
            }
        } catch (error) {
            console.error('Health check failed:', error);
        }
        connectionBadge.className = 'status-badge status-error';
        connectionStatus.textContent = 'API Offline';
        return false;
    }

    // Run initial health check and list documents
    checkHealth().then((isOnline) => {
        if (isOnline) {
            fetchDocuments();
        }
    });

    // Auto health check every 15 seconds
    setInterval(checkHealth, 15000);

    // ==========================================================================
    // 2. Document Ingestion & Management
    // ==========================================================================
    
    // Fetch and render list of ingested documents
    async function fetchDocuments() {
        try {
            const response = await fetch(`${API_BASE}/documents`);
            if (!response.ok) throw new Error('Failed to fetch documents');
            const docs = await response.json();
            renderDocumentSelect(docs);
            renderDocumentList(docs);
        } catch (error) {
            console.error('Error fetching documents:', error);
            showNotification('Error', 'Failed to retrieve ingested documents list.', 'danger');
        }
    }

    refreshDocsBtn.addEventListener('click', fetchDocuments);

    // Render dropdown selector
    function renderDocumentSelect(docs) {
        // Keep the default option
        const currentVal = docSelect.value;
        docSelect.innerHTML = '<option value="" disabled selected>Select a document...</option>';
        
        if (docs.length === 0) {
            updateChatControlsState();
            return;
        }

        docs.forEach(doc => {
            const option = document.createElement('option');
            option.value = doc.document_id;
            option.textContent = doc.filename || doc.document_id;
            docSelect.appendChild(option);
        });

        // Restore value if it still exists
        if (docs.some(d => d.document_id === currentVal)) {
            docSelect.value = currentVal;
            activeDocumentId = currentVal;
        } else {
            activeDocumentId = '';
        }
        updateChatControlsState();
    }

    // Render left panel document list
    function renderDocumentList(docs) {
        if (docs.length === 0) {
            documentsList.innerHTML = `
                <div class="empty-docs-placeholder">
                    <i class="fa-solid fa-inbox"></i>
                    <p>No documents ingested yet.</p>
                </div>
            `;
            return;
        }

        documentsList.innerHTML = '';
        docs.forEach(doc => {
            const pageCount = doc.pages ? doc.pages.length : 0;
            const docId = doc.document_id;
            const isSelected = docId === activeDocumentId;

            const docItem = document.createElement('div');
            docItem.className = `doc-item ${isSelected ? 'active-item' : ''}`;
            docItem.setAttribute('data-id', docId);

            docItem.innerHTML = `
                <div class="doc-info">
                    <i class="fa-regular fa-file-pdf doc-info-icon"></i>
                    <div class="doc-details">
                        <div class="doc-name" title="${doc.filename || docId}">${doc.filename || docId}</div>
                        <div class="doc-meta">${pageCount} pages • ${doc.chunks} chunks</div>
                    </div>
                </div>
                <button class="icon-btn delete-btn" title="Delete document" data-id="${docId}">
                    <i class="fa-regular fa-trash-can"></i>
                </button>
            `;

            // Make selecting item from list select it in the dropdown too
            docItem.addEventListener('click', (e) => {
                if (e.target.closest('.delete-btn')) return; // ignore delete clicks
                docSelect.value = docId;
                handleDocumentChange(docId);
            });

            // Handle delete button
            const deleteBtn = docItem.querySelector('.delete-btn');
            deleteBtn.addEventListener('click', async (e) => {
                e.stopPropagation();
                if (confirm(`Are you sure you want to delete "${doc.filename || docId}"? This will clear its database index.`)) {
                    await deleteDocument(docId);
                }
            });

            documentsList.appendChild(docItem);
        });
    }

    // Handle document selection change
    docSelect.addEventListener('change', (e) => {
        handleDocumentChange(e.target.value);
    });

    function handleDocumentChange(docId) {
        activeDocumentId = docId;
        updateChatControlsState();
        
        // Highlight active document in list
        const items = documentsList.querySelectorAll('.doc-item');
        items.forEach(item => {
            if (item.getAttribute('data-id') === docId) {
                item.classList.add('active-item');
            } else {
                item.classList.remove('active-item');
            }
        });

        // Add a small system notification in chat
        appendSystemMessage(`Target document switched to: ${docSelect.options[docSelect.selectedIndex].text}`);
    }

    // Delete document API call
    async function deleteDocument(docId) {
        try {
            const response = await fetch(`${API_BASE}/documents/${docId}`, {
                method: 'DELETE'
            });
            if (!response.ok) throw new Error('Deletion failed');
            
            showNotification('Success', 'Document deleted successfully.', 'success');
            
            if (activeDocumentId === docId) {
                activeDocumentId = '';
                docSelect.value = '';
            }
            
            await fetchDocuments();
        } catch (error) {
            console.error('Error deleting document:', error);
            showNotification('Error', 'Failed to delete the document.', 'danger');
        }
    }

    // State controller for enabling/disabling Chat Inputs
    function updateChatControlsState() {
        if (activeDocumentId) {
            chatInput.removeAttribute('disabled');
            chatSubmit.removeAttribute('disabled');
            chatAlert.classList.add('hidden');
        } else {
            chatInput.setAttribute('disabled', 'true');
            chatSubmit.setAttribute('disabled', 'true');
            chatAlert.classList.remove('hidden');
        }
    }

    // ==========================================================================
    // Drag & Drop / File Upload Actions
    // ==========================================================================
    
    // Trigger hidden file input on click
    dropZone.addEventListener('click', () => fileInput.click());

    // Highlight dropzone on dragover
    ['dragenter', 'dragover'].forEach(eventName => {
        dropZone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropZone.classList.add('dragover');
        }, false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropZone.classList.remove('dragover');
        }, false);
    });

    // Handle dropped file
    dropZone.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        const files = dt.files;
        if (files.length > 0) {
            handleFileUpload(files[0]);
        }
    });

    // Handle selected file
    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            handleFileUpload(e.target.files[0]);
        }
    });

    // Perform Ingestion Upload
    function handleFileUpload(file) {
        if (!file.name.toLowerCase().endsWith('.pdf')) {
            showNotification('Invalid File', 'Only PDF files are supported.', 'danger');
            return;
        }

        // Setup progress UI
        uploadFilename.textContent = file.name;
        uploadPercentage.textContent = '0%';
        uploadProgressBar.style.width = '0%';
        uploadStatusMessage.textContent = 'Uploading file...';
        uploadProgressContainer.classList.remove('hidden');
        
        // Disable drop zone during upload
        dropZone.style.pointerEvents = 'none';
        dropZone.style.opacity = '0.5';

        const formData = new FormData();
        formData.append('file', file);

        const xhr = new XMLHttpRequest();
        
        // Track file upload progress
        xhr.upload.onprogress = (e) => {
            if (e.lengthComputable) {
                const percentComplete = Math.round((e.loaded / e.total) * 100);
                uploadPercentage.textContent = `${percentComplete}%`;
                uploadProgressBar.style.width = `${percentComplete}%`;
                if (percentComplete === 100) {
                    uploadStatusMessage.textContent = 'Processing PDF (running extractors & Gemini models)... This might take a minute.';
                }
            }
        };

        xhr.onload = async () => {
            // Re-enable drop zone
            dropZone.style.pointerEvents = 'auto';
            dropZone.style.opacity = '1';

            if (xhr.status >= 200 && xhr.status < 300) {
                try {
                    const response = JSON.parse(xhr.responseText);
                    uploadStatusMessage.textContent = 'Ingestion Completed!';
                    showNotification('Success', `Ingested "${response.filename}" successfully.`, 'success');
                    
                    // Reload and select this new document
                    await fetchDocuments();
                    docSelect.value = response.document_id;
                    handleDocumentChange(response.document_id);
                    
                    // Log ingestion statistics to chat
                    appendSystemMessage(`
                        <strong>PDF Ingestion Complete:</strong><br>
                        • Pages Processed: ${response.pages_processed}<br>
                        • Vector Chunks Created: ${response.chunks_created}<br>
                        • Tables Extracted: ${response.tables_extracted}<br>
                        • Visual/Chart Captions: ${response.visual_chunks_extracted}
                    `);

                    setTimeout(() => {
                        uploadProgressContainer.classList.add('hidden');
                    }, 4000);
                } catch (e) {
                    console.error('Error parsing response:', e);
                    uploadStatusMessage.textContent = 'Ingestion processing failed.';
                    showNotification('Error', 'Failed to process document ingestion.', 'danger');
                }
            } else {
                let errMsg = 'Ingestion failed.';
                try {
                    const errObj = JSON.parse(xhr.responseText);
                    errMsg = errObj.detail || errMsg;
                } catch (_) {}
                uploadStatusMessage.textContent = errMsg;
                showNotification('Upload Error', errMsg, 'danger');
            }
        };

        xhr.onerror = () => {
            dropZone.style.pointerEvents = 'auto';
            dropZone.style.opacity = '1';
            uploadStatusMessage.textContent = 'Network error during upload.';
            showNotification('Error', 'Network connection interrupted.', 'danger');
        };

        xhr.open('POST', `${API_BASE}/ingest`, true);
        xhr.send(formData);
    }

    // ==========================================================================
    // 3. QA Chat System
    // ==========================================================================
    
    // Clear chat handler
    clearChatBtn.addEventListener('click', () => {
        chatMessages.innerHTML = `
            <div class="system-message">
                <div class="message-icon"><i class="fa-solid fa-circle-info"></i></div>
                <div class="message-text">
                    Chat history cleared. Select a document and type a question below to start fresh.
                </div>
            </div>
        `;
        messageSourcesStore = {};
    });

    // Form submit handler
    chatForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const text = chatInput.value.trim();
        if (!text) return;

        // Clear input field
        chatInput.value = '';

        // Render user message bubble
        appendChatBubble('user', text);
        
        // Render typing indicator
        const typingBubbleId = appendTypingIndicator();

        try {
            const response = await fetch(`${API_BASE}/query`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    document_id: activeDocumentId,
                    question: text,
                    top_k: 5
                })
            });

            // Remove typing spinner
            removeTypingIndicator(typingBubbleId);

            if (!response.ok) {
                const errData = await response.json().catch(() => ({ detail: 'Unknown error occurred.' }));
                appendChatBubble('assistant', `Error: ${errData.detail || 'Failed to get a response.'}`, [], true);
                return;
            }

            const data = await response.json();
            
            // Format sources metadata in the chat bubble
            const messageId = 'msg-' + Date.now();
            messageSourcesStore[messageId] = data.sources;
            
            appendChatBubble('assistant', data.answer, data.sources, false, messageId);

        } catch (error) {
            console.error('Error submitting query:', error);
            removeTypingIndicator(typingBubbleId);
            appendChatBubble('assistant', 'Connection error. Please check if your backend is running.', [], true);
        }
    });

    // Helper to format timestamps
    function getFormattedTime() {
        const date = new Date();
        return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }

    // Append Message Bubble DOM elements
    function appendChatBubble(sender, text, sources = [], isError = false, messageId = null) {
        const bubble = document.createElement('div');
        bubble.className = `message-bubble ${sender}`;
        if (messageId) bubble.setAttribute('id', messageId);

        const avatarIcon = sender === 'user' ? 'fa-regular fa-user' : 'fa-solid fa-robot';
        const formattedTime = getFormattedTime();
        
        // Escape HTML for safety, but allow linebreaks
        let escapedText = text
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;")
            .replace(/\n/g, '<br>');

        // Basic markdown parser for bold styling (**text**)
        escapedText = escapedText.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');

        let sourcesHtml = '';
        if (sources && sources.length > 0) {
            sourcesHtml = `<div class="source-citations">`;
            sources.forEach((src, idx) => {
                const typeIcon = getChunkTypeIcon(src.type);
                const scorePercent = src.score ? Math.round(src.score * 100) : null;
                const scorePill = scorePercent !== null ? `<span class="score-pill">${scorePercent}%</span>` : '';
                
                sourcesHtml += `
                    <span class="source-ref-badge" data-msg-id="${messageId}" data-index="${idx}" title="Click to view full reference text">
                        <i class="${typeIcon}"></i> Page ${src.page} ${scorePill}
                    </span>
                `;
            });
            sourcesHtml += `</div>`;
        }

        bubble.innerHTML = `
            <div class="message-avatar">
                <i class="${avatarIcon}"></i>
            </div>
            <div class="message-content">
                <div class="message-meta">
                    <span>${sender === 'user' ? 'You' : 'AI Assistant'}</span>
                    <span>${formattedTime}</span>
                </div>
                <div class="message-text-wrapper" style="${isError ? 'border-color: rgba(239,68,68,0.4); background: rgba(239,68,68,0.05);' : ''}">
                    ${escapedText}
                </div>
                ${sourcesHtml}
            </div>
        `;

        chatMessages.appendChild(bubble);
        scrollToBottom();

        // Register event click listeners for source badges
        if (messageId && sources.length > 0) {
            const badges = bubble.querySelectorAll('.source-ref-badge');
            badges.forEach(badge => {
                badge.addEventListener('click', () => {
                    const msgId = badge.getAttribute('data-msg-id');
                    const index = parseInt(badge.getAttribute('data-index'), 10);
                    const sourceData = messageSourcesStore[msgId][index];
                    openSourceModal(sourceData);
                });
            });
        }
    }

    // Append system status message bubble
    function appendSystemMessage(htmlContent) {
        const bubble = document.createElement('div');
        bubble.className = 'system-message';
        bubble.innerHTML = `
            <div class="message-icon"><i class="fa-solid fa-circle-info"></i></div>
            <div class="message-text">${htmlContent}</div>
        `;
        chatMessages.appendChild(bubble);
        scrollToBottom();
    }

    // Show Typing Indicator
    function appendTypingIndicator() {
        const bubbleId = 'typing-' + Date.now();
        const bubble = document.createElement('div');
        bubble.className = 'message-bubble assistant';
        bubble.setAttribute('id', bubbleId);
        
        bubble.innerHTML = `
            <div class="message-avatar">
                <i class="fa-solid fa-robot"></i>
            </div>
            <div class="message-content">
                <div class="message-meta">
                    <span>AI Assistant</span>
                </div>
                <div class="message-text-wrapper">
                    <div class="typing-indicator">
                        <span></span>
                        <span></span>
                        <span></span>
                    </div>
                </div>
            </div>
        `;
        chatMessages.appendChild(bubble);
        scrollToBottom();
        return bubbleId;
    }

    function removeTypingIndicator(id) {
        const elem = document.getElementById(id);
        if (elem) elem.remove();
    }

    function scrollToBottom() {
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function getChunkTypeIcon(type) {
        switch (type) {
            case 'text': return 'fa-solid fa-align-left';
            case 'table': return 'fa-solid fa-table';
            case 'visual':
            case 'chart':
            case 'image_caption': return 'fa-regular fa-image';
            default: return 'fa-solid fa-file-invoice';
        }
    }

    // ==========================================================================
    // 4. Source Detail Modal
    // ==========================================================================
    function openSourceModal(source) {
        // Classify Badge class
        let badgeClass = 'text-badge';
        let badgeLabel = 'Text Chunk';
        if (source.type === 'table') {
            badgeClass = 'table-badge';
            badgeLabel = 'Table Markdown';
        } else if (['visual', 'chart', 'image_caption'].includes(source.type)) {
            badgeClass = 'visual-badge';
            badgeLabel = 'Visual Caption';
        }

        modalSourceBadge.className = `source-badge ${badgeClass}`;
        modalSourceBadge.textContent = badgeLabel;
        modalSourceTitle.textContent = source.title || `Source: Page ${source.page}`;
        modalPageNum.textContent = source.page;
        modalScore.textContent = source.score ? source.score.toFixed(4) : 'N/A';
        modalChunkId.textContent = source.chunk_id;
        modalExcerptText.textContent = source.excerpt;

        sourceModal.classList.remove('hidden');
    }

    function closeModal() {
        sourceModal.classList.add('hidden');
    }

    closeModalBtn.addEventListener('click', closeModal);
    modalBackdrop.addEventListener('click', closeModal);

    // Escape key press to close modal
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && !sourceModal.classList.contains('hidden')) {
            closeModal();
        }
    });

    // ==========================================================================
    // UI Helpers (Toast Notifications)
    // ==========================================================================
    function showNotification(title, text, type = 'info') {
        const toast = document.createElement('div');
        toast.className = `chat-alert`;
        toast.style.position = 'fixed';
        toast.style.bottom = '20px';
        toast.style.right = '20px';
        toast.style.zIndex = '9999';
        toast.style.width = '300px';
        toast.style.boxShadow = 'var(--shadow-lg)';
        toast.style.background = type === 'success' ? 'var(--success-bg)' : type === 'danger' ? 'var(--danger-bg)' : 'rgba(30,41,59,0.95)';
        toast.style.borderColor = type === 'success' ? 'var(--border-success)' : type === 'danger' ? 'rgba(239,68,68,0.5)' : 'var(--border-color)';
        toast.style.color = 'white';

        const icon = type === 'success' ? 'fa-circle-check' : type === 'danger' ? 'fa-circle-xmark' : 'fa-circle-info';
        const color = type === 'success' ? 'var(--success)' : type === 'danger' ? 'var(--danger)' : 'var(--info)';

        toast.innerHTML = `
            <i class="fa-solid ${icon}" style="color: ${color}"></i>
            <div>
                <strong style="display:block;font-size:12px;">${title}</strong>
                <span style="font-size:11px;opacity:0.9;">${text}</span>
            </div>
        `;

        document.body.appendChild(toast);

        setTimeout(() => {
            toast.style.transition = 'opacity 0.5s ease';
            toast.style.opacity = '0';
            setTimeout(() => toast.remove(), 500);
        }, 4000);
    }
});
