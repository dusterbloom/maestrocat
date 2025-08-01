// ui/modules/amem.js
const amemView = document.getElementById('amem-view');
const amemSearch = document.getElementById('amem-search');
const amemSearchButton = document.getElementById('amem-search-button');
const amemListAllButton = document.getElementById('amem-list-all-button');

const API_BASE_URL = ''; // All API calls are relative to the current host

let memories = [];

export async function initAMem() {
    await fetchMemories();
    renderMemories();

    amemSearchButton.addEventListener('click', () => {
        if (window.maestroCatApp && window.maestroCatApp.websocket) {
            window.maestroCatApp.websocket.send('amem_search', { query: amemSearch.value });
        } else {
            console.error("Cannot send amem_search event: WebSocket manager not available.");
        }
    });

    amemListAllButton.addEventListener('click', async () => {
        try {
            const response = await fetch(`${API_BASE_URL}/api/amem/all`);
            const allMemories = await response.json();
            memories = allMemories;
            renderMemories();
        } catch (error) {
            console.error('Error fetching all A-Mem memories:', error);
        }
    });
}

async function fetchMemories() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/amem`);
        memories = await response.json();
        renderMemories();
    } catch (error) {
        console.error('Error fetching A-Mem memories:', error);
    }
}

function renderMemories(filter = '') {
    amemView.innerHTML = '';
    const filteredMemories = memories.filter(mem =>
        (mem.content && mem.content.toLowerCase().includes(filter.toLowerCase())) ||
        (mem.metadata.title && mem.metadata.title.toLowerCase().includes(filter.toLowerCase()))
    );

    filteredMemories.forEach(mem => {
        const memElement = document.createElement('div');
        memElement.className = 'amem-note';
        memElement.innerHTML = `
            <div class="amem-note-header">
                <h4 class="amem-note-title">${mem.metadata.title || 'Untitled'}</h4>
                <span class="amem-note-id">${mem.id.substring(0, 8)}</span>
            </div>
            <div class="amem-note-body">
                <p>${mem.content}</p>
            </div>
            <div class="amem-note-footer">
                <div class="amem-note-tags">
                    ${(Array.isArray(mem.metadata.tags) ? mem.metadata.tags : (mem.metadata.tags || "").split(',')).map(tag => tag.trim() ? `<span class="amem-note-tag">${tag}</span>` : '').join('')}
                </div>
                <div class="amem-note-links">
                    ${(Array.isArray(mem.metadata.links) ? mem.metadata.links : (mem.metadata.links || "").split(',')).map(link => link.trim() ? `<a href="#" class="amem-note-link" data-id="${link}">${link.substring(0, 8)}</a>` : '').join('')}
                </div>
            </div>
        `;
        amemView.appendChild(memElement);
    });
}

export function handleAMemUpdate(event) {
    const newMemory = event.data;
    const index = memories.findIndex(mem => mem.id === newMemory.id);
    if (index > -1) {
        memories[index] = newMemory;
    } else {
        memories.push(newMemory);
    }
    renderMemories(amemSearch.value);
}
