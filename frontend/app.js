/**
 * Content Registry — Frontend Application Logic
 */

document.addEventListener('DOMContentLoaded', () => {
  // --- APPLICATION STATE ---
  const state = {
    activeTab: 'dashboard', // dashboard, upload, explore
    files: [],
    metadata: {
      classes: [],
      subjects: [],
      chapters: []
    },
    filters: {
      class_name: '',
      subject: '',
      chapter: '',
      search: ''
    },
    layout: 'grid', // grid, list
    activeFile: null,
    sseActive: false,
    lastExtractedFileId: null
  };

  // --- DOM ELEMENTS ---
  const DOM = {
    navItems: document.querySelectorAll('.nav-item'),
    viewSections: document.querySelectorAll('.view-section'),
    viewTitle: document.getElementById('view-title'),
    viewSubtitle: document.getElementById('view-subtitle'),

    // Stats
    statTotalDocs: document.getElementById('stat-total-docs'),
    statTotalClasses: document.getElementById('stat-total-classes'),
    statTotalSubjects: document.getElementById('stat-total-subjects'),
    dashboardRecentList: document.getElementById('dashboard-recent-list'),
    btnViewAllDashboard: document.getElementById('btn-view-all-dashboard'),
    qaUpload: document.getElementById('qa-upload'),
    qaBrowse: document.getElementById('qa-browse'),

    // Upload Tab
    uploadForm: document.getElementById('upload-form'),
    dropZone: document.getElementById('drop-zone'),
    fileInput: document.getElementById('file-input'),
    fileBanner: document.getElementById('file-banner'),
    selectedFilename: document.querySelector('.selected-filename'),
    selectedFilesize: document.querySelector('.selected-filesize'),
    btnRemoveFile: document.getElementById('btn-remove-file'),
    classSelect: document.getElementById('class-select'),
    subjectSelect: document.getElementById('subject-select'),
    chapterSelect: document.getElementById('chapter-select'),
    chapterCustomContainer: document.getElementById('chapter-custom-container'),
    chapterCustomInput: document.getElementById('chapter-custom-input'),
    docDescription: document.getElementById('doc-description'),
    docTags: document.getElementById('doc-tags'),
    btnSubmitUpload: document.getElementById('btn-submit-upload'),

    // Progress/SSE Console
    sseProgressCard: document.getElementById('sse-progress-card'),
    consoleStatusBadge: document.getElementById('console-status-badge'),
    sseProgressFill: document.getElementById('sse-progress-fill'),
    sseProgressPercent: document.getElementById('sse-progress-percent'),
    sseProgressMessage: document.getElementById('sse-progress-message'),
    sseLogs: document.getElementById('sse-logs'),
    consoleActions: document.getElementById('console-actions'),
    btnViewExtracted: document.getElementById('btn-view-extracted'),

    // Explore Tab
    searchQuery: document.getElementById('search-query'),
    filterClass: document.getElementById('filter-class'),
    filterSubject: document.getElementById('filter-subject'),
    filterChapter: document.getElementById('filter-chapter'),
    btnResetFilters: document.getElementById('btn-reset-filters'),
    resultsCount: document.getElementById('results-count'),
    layoutGrid: document.getElementById('layout-grid'),
    layoutList: document.getElementById('layout-list'),
    filesGrid: document.getElementById('files-grid'),

    // Detail Drawer
    drawerOverlay: document.getElementById('drawer-overlay'),
    detailDrawer: document.getElementById('detail-drawer'),
    btnCloseDrawer: document.getElementById('btn-close-drawer'),
    drawerBtnDownload: document.getElementById('drawer-btn-download'),
    drawerBtnDelete: document.getElementById('drawer-btn-delete'),
    drawerClass: document.getElementById('drawer-class'),
    drawerSubject: document.getElementById('drawer-subject'),
    drawerFilename: document.getElementById('drawer-filename'),
    drawerChapter: document.getElementById('drawer-chapter'),
    drawerDescription: document.getElementById('drawer-description'),
    drawerTags: document.getElementById('drawer-tags'),
    drawerDate: document.getElementById('drawer-date'),
    drawerSize: document.getElementById('drawer-size'),
    drawerTabs: document.querySelectorAll('.drawer-tab'),
    tabPanes: document.querySelectorAll('.tab-pane'),
    notExtractedBlock: document.getElementById('not-extracted-block'),
    btnTriggerExtraction: document.getElementById('btn-trigger-extraction'),
    drawerRenderedMd: document.getElementById('drawer-rendered-md'),
    drawerRawMd: document.getElementById('drawer-raw-md'),
    btnCopyRaw: document.getElementById('btn-copy-raw')
  };

  // --- INITIALIZATION ---
  async function init() {
    registerEventListeners();
    await loadMetadata();
    await fetchFiles();
    updateDashboardStats();
  }

  // --- EVENT REGISTRATION ---
  function registerEventListeners() {
    // Sidebar tabs navigation
    DOM.navItems.forEach(item => {
      item.addEventListener('click', (e) => {
        e.preventDefault();
        const tab = item.getAttribute('data-tab');
        switchTab(tab);
      });
    });

    // Quick actions on dashboard
    DOM.qaUpload.addEventListener('click', () => switchTab('upload'));
    DOM.qaBrowse.addEventListener('click', () => switchTab('explore'));
    DOM.btnViewAllDashboard.addEventListener('click', () => switchTab('explore'));

    // Drag and Drop events
    DOM.dropZone.addEventListener('click', () => DOM.fileInput.click());
    DOM.fileInput.addEventListener('change', handleFileSelect);

    ['dragenter', 'dragover'].forEach(eventName => {
      DOM.dropZone.addEventListener(eventName, (e) => {
        e.preventDefault();
        DOM.dropZone.classList.add('dragover');
      }, false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
      DOM.dropZone.addEventListener(eventName, (e) => {
        e.preventDefault();
        DOM.dropZone.classList.remove('dragover');
      }, false);
    });

    DOM.dropZone.addEventListener('drop', (e) => {
      const dt = e.dataTransfer;
      const files = dt.files;
      if (files.length > 0) {
        DOM.fileInput.files = files;
        handleFileSelect();
      }
    });

    DOM.btnRemoveFile.addEventListener('click', (e) => {
      e.stopPropagation();
      resetFileSelection();
    });

    // Dynamic dropdown cascade
    DOM.classSelect.addEventListener('change', () => {
      updateDynamicChapters(DOM.classSelect.value, DOM.subjectSelect.value);
    });
    DOM.subjectSelect.addEventListener('change', () => {
      updateDynamicChapters(DOM.classSelect.value, DOM.subjectSelect.value);
    });
    DOM.chapterSelect.addEventListener('change', () => {
      if (DOM.chapterSelect.value === '__custom__') {
        DOM.chapterCustomContainer.style.display = 'block';
        DOM.chapterCustomInput.required = true;
      } else {
        DOM.chapterCustomContainer.style.display = 'none';
        DOM.chapterCustomInput.required = false;
      }
    });

    // Upload submission
    DOM.uploadForm.addEventListener('submit', handleUploadSubmit);

    // Filters and search logic
    DOM.searchQuery.addEventListener('input', debounce(() => {
      state.filters.search = DOM.searchQuery.value;
      fetchFiles();
    }, 300));

    DOM.filterClass.addEventListener('change', () => {
      state.filters.class_name = DOM.filterClass.value;
      fetchFiles();
    });

    DOM.filterSubject.addEventListener('change', () => {
      state.filters.subject = DOM.filterSubject.value;
      fetchFiles();
    });

    DOM.filterChapter.addEventListener('change', () => {
      state.filters.chapter = DOM.filterChapter.value;
      fetchFiles();
    });

    DOM.btnResetFilters.addEventListener('click', () => {
      DOM.searchQuery.value = '';
      DOM.filterClass.value = '';
      DOM.filterSubject.value = '';
      DOM.filterChapter.value = '';

      state.filters = { class_name: '', subject: '', chapter: '', search: '' };
      fetchFiles();
    });

    // Layout Toggle
    DOM.layoutGrid.addEventListener('click', () => setLayout('grid'));
    DOM.layoutList.addEventListener('click', () => setLayout('list'));

    // Drawer overlay close
    DOM.drawerOverlay.addEventListener('click', closeDrawer);
    DOM.btnCloseDrawer.addEventListener('click', closeDrawer);

    // Drawer tabs switcher
    DOM.drawerTabs.forEach(tab => {
      tab.addEventListener('click', () => {
        DOM.drawerTabs.forEach(t => t.classList.remove('active'));
        DOM.tabPanes.forEach(p => p.classList.remove('active'));

        tab.classList.add('active');
        const paneId = tab.getAttribute('data-pane');
        document.getElementById(paneId).classList.add('active');
      });
    });

    // Manual extraction trigger
    DOM.btnTriggerExtraction.addEventListener('click', triggerManualExtraction);

    // Copy raw markdown button
    DOM.btnCopyRaw.addEventListener('click', () => {
      DOM.drawerRawMd.select();
      document.execCommand('copy');
      const origText = DOM.btnCopyRaw.innerHTML;
      DOM.btnCopyRaw.innerHTML = '<i class="fa-solid fa-check"></i> Copied!';
      setTimeout(() => {
        DOM.btnCopyRaw.innerHTML = origText;
      }, 2000);
    });

    // Drawer delete button
    DOM.drawerBtnDelete.addEventListener('click', () => {
      if (state.activeFile) {
        deleteFile(state.activeFile.id);
      }
    });

    // View extracted content from upload console
    if (DOM.btnViewExtracted) {
      DOM.btnViewExtracted.addEventListener('click', async () => {
        const fileId = state.lastExtractedFileId;
        if (!fileId) return;

        try {
          const res = await fetch(`/api/content/${fileId}`);
          if (!res.ok) throw new Error('File not found');
          const file = await res.json();
          openDrawer(file);
        } catch (err) {
          alert(`Error opening file: ${err.message}`);
        }
      });
    }
  }

  // --- CORE LOGIC & ACTIONS ---

  function switchTab(tab) {
    state.activeTab = tab;

    // Update Menu selection
    DOM.navItems.forEach(item => {
      if (item.getAttribute('data-tab') === tab) {
        item.classList.add('active');
      } else {
        item.classList.remove('active');
      }
    });

    // Update section visibility
    DOM.viewSections.forEach(section => {
      if (section.id === `${tab}-view`) {
        section.classList.add('active');
      } else {
        section.classList.remove('active');
      }
    });

    // Update headers
    if (tab === 'dashboard') {
      DOM.viewTitle.innerText = 'Dashboard';
      DOM.viewSubtitle.innerText = 'Overview of your educational resource repository';
      updateDashboardStats();
    } else if (tab === 'upload') {
      DOM.viewTitle.innerText = 'Intake Portal';
      DOM.viewSubtitle.innerText = 'Upload files and automatically parse layout, text, and LaTeX equations';
    } else if (tab === 'explore') {
      DOM.viewTitle.innerText = 'Explore Registry';
      DOM.viewSubtitle.innerText = 'Search and manage all educational assets';
      fetchFiles();
    }
  }

  // METADATA FETCHING
  async function loadMetadata() {
    try {
      const [classRes, subjectRes, chapterRes] = await Promise.all([
        fetch('/api/metadata/classes').then(r => r.json()),
        fetch('/api/metadata/subjects').then(r => r.json()),
        fetch('/api/metadata/chapters').then(r => r.json())
      ]);

      state.metadata.classes = classRes.values || [];
      state.metadata.subjects = subjectRes.values || [];
      state.metadata.chapters = chapterRes.values || [];

      // Populate selects
      populateSelectOptions(DOM.classSelect, state.metadata.classes, 'Select class...');
      populateSelectOptions(DOM.subjectSelect, state.metadata.subjects, 'Select subject...');

      // Explore Filter selects
      populateSelectOptions(DOM.filterClass, state.metadata.classes, 'All Classes');
      populateSelectOptions(DOM.filterSubject, state.metadata.subjects, 'All Subjects');
      populateSelectOptions(DOM.filterChapter, state.metadata.chapters, 'All Chapters');

      updateDynamicChapters(null, null);
    } catch (err) {
      console.error('Failed to load metadata', err);
    }
  }

  function populateSelectOptions(selectElement, array, defaultLabel) {
    selectElement.innerHTML = `<option value="" disabled selected>${defaultLabel}</option>`;
    if (defaultLabel.includes('All')) {
      selectElement.innerHTML = `<option value="">${defaultLabel}</option>`;
    }
    array.forEach(val => {
      const opt = document.createElement('option');
      opt.value = val;
      opt.innerText = val;
      selectElement.appendChild(opt);
    });
  }

  async function updateDynamicChapters(selectedClass, selectedSubject) {
    if (!selectedClass && !selectedSubject) {
      DOM.chapterSelect.innerHTML = `<option value="" disabled selected>Select class & subject first...</option>`;
      return;
    }

    let url = '/api/metadata/chapters?';
    if (selectedClass) url += `class_name=${encodeURIComponent(selectedClass)}&`;
    if (selectedSubject) url += `subject=${encodeURIComponent(selectedSubject)}`;

    try {
      const res = await fetch(url);
      const data = await res.json();
      const chapters = data.values || [];

      DOM.chapterSelect.innerHTML = `<option value="" disabled selected>Select chapter...</option>`;
      chapters.forEach(ch => {
        const opt = document.createElement('option');
        opt.value = ch;
        opt.innerText = ch;
        DOM.chapterSelect.appendChild(opt);
      });

      // Add a custom option
      const customOpt = document.createElement('option');
      customOpt.value = '__custom__';
      customOpt.innerText = '✏️ Custom Chapter...';
      DOM.chapterSelect.appendChild(customOpt);
    } catch (err) {
      console.error('Failed to load dynamic chapters', err);
    }
  }

  // FILE SELECTION
  function handleFileSelect() {
    const file = DOM.fileInput.files[0];
    if (!file) return;

    DOM.selectedFilename.innerText = file.name;
    DOM.selectedFilesize.innerText = formatBytes(file.size);

    // Toggle displays
    DOM.dropZone.querySelector('.drop-zone-content').style.display = 'none';
    DOM.fileBanner.style.display = 'flex';
  }

  function resetFileSelection() {
    DOM.fileInput.value = '';
    DOM.dropZone.querySelector('.drop-zone-content').style.display = 'block';
    DOM.fileBanner.style.display = 'none';
  }

  // SSE UPLOAD & EXTRACTION FLOW
  async function handleUploadSubmit(e) {
    e.preventDefault();

    const file = DOM.fileInput.files[0];
    if (!file) {
      alert('Please select a file to upload first.');
      return;
    }

    const className = DOM.classSelect.value;
    const subject = DOM.subjectSelect.value;
    let chapter = DOM.chapterSelect.value;

    if (chapter === '__custom__') {
      chapter = DOM.chapterCustomInput.value.trim();
      if (!chapter) {
        alert('Please specify the custom chapter name.');
        return;
      }
    }

    const description = DOM.docDescription.value.trim();
    const tagsRaw = DOM.docTags.value.split(',').map(t => t.trim()).filter(Boolean);
    const tagsJson = JSON.stringify(tagsRaw);

    const formData = new FormData();
    formData.append('file', file);
    formData.append('class_name', className);
    formData.append('subject', subject);
    formData.append('chapter', chapter);
    formData.append('description', description);
    formData.append('tags', tagsJson);

    // Lock Submit UI
    DOM.btnSubmitUpload.disabled = true;
    DOM.btnSubmitUpload.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Initializing SSE Upload...';

    // Reset view action buttons
    if (DOM.consoleActions) DOM.consoleActions.style.display = 'none';
    state.lastExtractedFileId = null;

    // Open Console
    DOM.sseProgressCard.classList.add('active');
    updateConsoleStatus('processing', 'Uploading and initiating extraction stream...');
    clearConsoleLogs();
    writeConsoleLog('SYSTEM', 'Connecting to upload-extract stream...');

    try {
      const response = await fetch('/api/content/upload-extract', {
        method: 'POST',
        body: formData
      });

      if (!response.ok) {
        throw new Error(await response.text());
      }

      // Read SSE stream manually from Fetch body
      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';

      writeConsoleLog('SYSTEM', 'Connection open. Processing data stream...');

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n\n');

        // Save the last partial block back to the buffer
        buffer = lines.pop();

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const dataStr = line.slice(6);
            try {
              const eventData = JSON.parse(dataStr);
              handleSSEMessage(eventData);
            } catch (err) {
              console.error('Error parsing SSE event data', err);
            }
          }
        }
      }
    } catch (err) {
      writeConsoleLog('ERROR', `Upload failed: ${err.message}`);
      updateConsoleStatus('failed', `Error: ${err.message}`);
      resetUploadButton();
    }
  }

  function handleSSEMessage(data) {
    const percent = data.percent || 0;
    const message = data.message || 'Processing...';
    const status = data.status || 'processing';

    // Update progress bar
    DOM.sseProgressFill.style.width = `${percent}%`;
    DOM.sseProgressPercent.innerText = `${percent}%`;
    DOM.sseProgressMessage.innerText = message;

    if (status === 'processing') {
      updateConsoleStatus('processing', message);
      writeConsoleLog('PROCESS', message);
    } else if (status === 'completed') {
      updateConsoleStatus('completed', 'Finished successfully!');
      writeConsoleLog('SUCCESS', `Extraction Done. ID: ${data.content_id}`);

      // Save last extracted content ID and show view action button
      state.lastExtractedFileId = data.content_id;
      if (DOM.consoleActions) DOM.consoleActions.style.display = 'block';

      // Reset form
      DOM.uploadForm.reset();
      resetFileSelection();
      DOM.chapterCustomContainer.style.display = 'none';

      // Reload UI data
      loadMetadata();
      fetchFiles();
      updateDashboardStats();
      resetUploadButton();
    } else if (status === 'failed') {
      updateConsoleStatus('failed', `Failed: ${message}`);
      writeConsoleLog('ERROR', `Failed extraction: ${message}`);
      resetUploadButton();
    }
  }

  function resetUploadButton() {
    DOM.btnSubmitUpload.disabled = false;
    DOM.btnSubmitUpload.innerHTML = '<i class="fa-solid fa-bolt"></i> Upload & Process (SSE)';
  }

  // EXPLORE AND FETCH FILES
  async function fetchFiles() {
    let url = '/api/content?';
    if (state.filters.class_name) url += `class_name=${encodeURIComponent(state.filters.class_name)}&`;
    if (state.filters.subject) url += `subject=${encodeURIComponent(state.filters.subject)}&`;
    if (state.filters.chapter) url += `chapter=${encodeURIComponent(state.filters.chapter)}&`;
    if (state.filters.search) url += `search=${encodeURIComponent(state.filters.search)}`;

    try {
      const res = await fetch(url);
      const data = await res.json();
      state.files = data.items || [];

      // Update count
      DOM.resultsCount.innerText = state.files.length;

      // Render
      renderFilesGrid();
    } catch (err) {
      console.error('Error fetching files', err);
    }
  }

  function renderFilesGrid() {
    DOM.filesGrid.innerHTML = '';

    if (state.files.length === 0) {
      DOM.filesGrid.innerHTML = `
        <div class="empty-state">
          <i class="fa-solid fa-folder-open"></i>
          <h3>No files found</h3>
          <p>Try refining your search filters or upload a new resource</p>
        </div>
      `;
      return;
    }

    state.files.forEach(file => {
      const card = document.createElement('div');
      card.className = `file-card ${state.layout === 'list' ? 'list-row' : ''}`;

      const fileIcon = getFileIconClass(file.filename);
      const dateStr = formatDate(file.created_at);
      const isExtracted = !!file.extracted_text;

      // JSON parsing of tags safely
      let tags = [];
      try {
        tags = JSON.parse(file.tags || '[]');
      } catch (e) { }

      card.innerHTML = `
        <div class="card-top">
          <div class="card-icon">
            <i class="${fileIcon}"></i>
          </div>
          <div class="card-metadata">
            <h3>${escapeHtml(file.filename)}</h3>
            <span class="chapter-tag">${escapeHtml(file.chapter)}</span>
          </div>
        </div>
        <p class="card-desc">${escapeHtml(file.description || 'No description provided.')}</p>
        <div class="card-badges">
          <span class="doc-badge primary">${escapeHtml(file.class_name)}</span>
          <span class="doc-badge secondary">${escapeHtml(file.subject)}</span>
          ${isExtracted ? '<span class="doc-badge gray"><i class="fa-solid fa-wand-magic-sparkles"></i> Extracted</span>' : ''}
        </div>
        <div class="card-footer">
          <span class="date">${dateStr} • ${formatBytes(file.filesize)}</span>
          <div class="actions">
            <button class="card-action-btn delete" data-id="${file.id}" title="Delete Resource">
              <i class="fa-regular fa-trash-can"></i>
            </button>
          </div>
        </div>
      `;

      card.addEventListener('click', (e) => {
        // Prevent opening drawer if they clicked delete button
        if (e.target.closest('.delete')) {
          e.stopPropagation();
          deleteFile(file.id);
          return;
        }
        openDrawer(file);
      });

      DOM.filesGrid.appendChild(card);
    });
  }

  // LAYOUT TOGGLER
  function setLayout(layout) {
    state.layout = layout;
    if (layout === 'grid') {
      DOM.layoutGrid.classList.add('active');
      DOM.layoutList.classList.remove('active');
      DOM.filesGrid.classList.remove('list-view');
    } else {
      DOM.layoutGrid.classList.remove('active');
      DOM.layoutList.classList.add('active');
      DOM.filesGrid.classList.add('list-view');
    }
    renderFilesGrid();
  }

  // DASHBOARD METRICS
  async function updateDashboardStats() {
    try {
      const res = await fetch('/api/content');
      const data = await res.json();
      const files = data.items || [];

      // Metrics
      const totalDocs = files.length;

      const uniqueClasses = new Set(files.map(f => f.class_name));
      const uniqueSubjects = new Set(files.map(f => f.subject));

      DOM.statTotalDocs.innerText = totalDocs;
      DOM.statTotalClasses.innerText = uniqueClasses.size;
      DOM.statTotalSubjects.innerText = uniqueSubjects.size;

      // Recent upload list (last 5)
      const sortedRecents = [...files].sort((a, b) => new Date(b.created_at) - new Date(a.created_at)).slice(0, 5);

      DOM.dashboardRecentList.innerHTML = '';
      if (sortedRecents.length === 0) {
        DOM.dashboardRecentList.innerHTML = `
          <div class="empty-state" style="padding: 20px;">
            <p>No recent uploads. Switch to the Upload tab to add some files!</p>
          </div>
        `;
        return;
      }

      sortedRecents.forEach(file => {
        const item = document.createElement('div');
        item.className = 'recent-item';
        const fileIcon = getFileIconClass(file.filename);

        item.innerHTML = `
          <div class="recent-meta">
            <i class="${fileIcon}" style="color: var(--color-primary); font-size: 1.1rem;"></i>
            <div class="recent-text">
              <span class="recent-title">${escapeHtml(file.filename)}</span>
              <div class="recent-sub">
                <span>${escapeHtml(file.class_name)} • ${escapeHtml(file.subject)}</span>
              </div>
            </div>
          </div>
          <span style="font-size: 0.75rem; color: var(--text-muted);">${formatDate(file.created_at)}</span>
        `;

        item.addEventListener('click', () => openDrawer(file));
        DOM.dashboardRecentList.appendChild(item);
      });

    } catch (err) {
      console.error('Failed to update stats dashboard', err);
    }
  }

  // DRAWER PANES CONTROL
  function openDrawer(file) {
    state.activeFile = file;

    // Fill text metadata
    DOM.drawerClass.innerText = file.class_name;
    DOM.drawerSubject.innerText = file.subject;
    DOM.drawerFilename.innerText = file.filename;
    DOM.drawerChapter.innerText = file.chapter;
    DOM.drawerDescription.innerText = file.description || 'No description.';
    DOM.drawerDate.innerText = formatDate(file.created_at);
    DOM.drawerSize.innerText = formatBytes(file.filesize);

    DOM.drawerBtnDownload.href = `/api/content/${file.id}/download`;

    // Render tags
    DOM.drawerTags.innerHTML = '';
    let tags = [];
    try { tags = JSON.parse(file.tags || '[]'); } catch (e) { }
    tags.forEach(t => {
      const span = document.createElement('span');
      span.className = 'doc-badge gray';
      span.innerText = t;
      DOM.drawerTags.appendChild(span);
    });

    // Reset tabs
    DOM.drawerTabs[0].click();

    // Check extraction state
    renderDocumentContent();

    // Show drawer
    DOM.drawerOverlay.classList.add('active');
    DOM.detailDrawer.classList.add('active');
  }

  function closeDrawer() {
    state.activeFile = null;
    DOM.drawerOverlay.classList.remove('active');
    DOM.detailDrawer.classList.remove('active');
  }

  function renderDocumentContent() {
    const file = state.activeFile;
    if (!file) return;

    if (file.extracted_text) {
      DOM.notExtractedBlock.style.display = 'none';
      DOM.drawerRenderedMd.style.display = 'block';
      DOM.drawerRawMd.value = file.extracted_text;

      // Perform path cleaning for HTML image downloads
      let markdown = file.extracted_text;

      // Convert Markdown image paths pointing to the backend's relative upload routes
      // The backend uses full Windows paths inside the DB field, we need to clean them up.
      markdown = markdown.replaceAll(/!\[(.*?)\]\((.*?)\)/g, (match, alt, path) => {
        if (path.startsWith('data:') || path.startsWith('http:') || path.startsWith('https:')) {
          return match;
        }
        let cleanPath = path.replace(/\\/g, '/');
        // If it looks like a local absolute path, swap it to use the web uploads route
        if (cleanPath.includes('/uploads/')) {
          cleanPath = '/uploads/' + cleanPath.split('/uploads/').pop();
        } else if (!cleanPath.startsWith('/')) {
          // Fallback guess
          cleanPath = '/uploads/' + cleanPath.split('/').pop();
        }
        return `![${alt}](${cleanPath})`;
      });

      // Parse with Marked.js
      DOM.drawerRenderedMd.innerHTML = marked.parse(markdown);

      // Trigger MathJax typeset
      if (window.MathJax && typeof window.MathJax.typesetPromise === 'function') {
        window.MathJax.typesetPromise([DOM.drawerRenderedMd]).catch(err => {
          console.error('MathJax formatting error', err);
        });
      }
    } else {
      DOM.notExtractedBlock.style.display = 'block';
      DOM.drawerRenderedMd.style.display = 'none';
      DOM.drawerRenderedMd.innerHTML = '';
      DOM.drawerRawMd.value = 'File has not been extracted.';
    }
  }

  // TRIGGER EXTRACTION MANUALLY
  async function triggerManualExtraction() {
    const file = state.activeFile;
    if (!file) return;

    const modeRadio = document.querySelector('input[name="extract-mode"]:checked');
    const mode = modeRadio ? modeRadio.value : 'fast';

    DOM.btnTriggerExtraction.disabled = true;
    DOM.btnTriggerExtraction.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Processing OCR Layout...';

    try {
      const res = await fetch(`/api/content/${file.id}/extract?mode=${mode}&background=false`, {
        method: 'POST'
      });

      if (!res.ok) {
        throw new Error(await res.text());
      }

      const data = await res.json();

      // Update state and DB records local copy
      file.extracted_text = data.extracted_text;
      state.files = state.files.map(f => f.id === file.id ? { ...f, extracted_text: data.extracted_text } : f);

      // Re-render
      renderDocumentContent();
      renderFilesGrid();
    } catch (err) {
      alert(`Manual Extraction Failed: ${err.message}`);
    } finally {
      DOM.btnTriggerExtraction.disabled = false;
      DOM.btnTriggerExtraction.innerHTML = '<i class="fa-solid fa-play"></i> Run Extraction Now';
    }
  }

  // DELETE RESOURCE
  async function deleteFile(id) {
    if (!confirm('Are you sure you want to permanently delete this resource from disk and registry?')) {
      return;
    }

    try {
      const res = await fetch(`/api/content/${id}`, {
        method: 'DELETE'
      });

      if (!res.ok) {
        throw new Error('Failed to delete file');
      }

      closeDrawer();
      fetchFiles();
      updateDashboardStats();
    } catch (err) {
      alert(`Error deleting resource: ${err.message}`);
    }
  }

  // --- HELPER UTILITIES ---

  function getFileIconClass(filename) {
    const ext = filename.split('.').pop().toLowerCase();
    switch (ext) {
      case 'pdf': return 'fa-regular fa-file-pdf';
      case 'doc':
      case 'docx': return 'fa-regular fa-file-word';
      case 'xls':
      case 'xlsx': return 'fa-regular fa-file-excel';
      case 'jpg':
      case 'jpeg':
      case 'png':
      case 'gif':
      case 'webp': return 'fa-regular fa-file-image';
      default: return 'fa-regular fa-file-code';
    }
  }

  function formatBytes(bytes, decimals = 2) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
  }

  function formatDate(isoString) {
    if (!isoString) return '-';
    const date = new Date(isoString);
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric'
    });
  }

  function escapeHtml(string) {
    const matchHtmlRegExp = /["'&<>]/;
    const str = '' + string;
    const match = matchHtmlRegExp.exec(str);
    if (!match) return str;

    let escape;
    let html = '';
    let index = 0;
    let lastIndex = 0;

    for (index = match.index; index < str.length; index++) {
      switch (str.charCodeAt(index)) {
        case 34: escape = '&quot;'; break; // "
        case 38: escape = '&amp;'; break;  // &
        case 39: escape = '&#39;'; break;  // '
        case 60: escape = '&lt;'; break;   // <
        case 62: escape = '&gt;'; break;   // >
        default: continue;
      }

      if (lastIndex !== index) {
        html += str.substring(lastIndex, index);
      }

      lastIndex = index + 1;
      html += escape;
    }

    return lastIndex !== index ? html + str.substring(lastIndex, index) : html;
  }

  function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
      const later = () => {
        clearTimeout(timeout);
        func(...args);
      };
      clearTimeout(timeout);
      timeout = setTimeout(later, wait);
    };
  }

  // Console log simulations
  function updateConsoleStatus(status, text) {
    DOM.consoleStatusBadge.className = `console-badge ${status}`;
    DOM.consoleStatusBadge.innerText = status.toUpperCase();
  }

  function clearConsoleLogs() {
    DOM.sseLogs.innerHTML = '';
  }

  function writeConsoleLog(level, msg) {
    const line = document.createElement('div');
    line.className = `log-line ${level.toLowerCase()}`;
    const timestamp = new Date().toLocaleTimeString();
    line.innerText = `[${timestamp}] [${level}] ${msg}`;
    DOM.sseLogs.appendChild(line);
    // Scroll to bottom
    DOM.sseLogs.scrollTop = DOM.sseLogs.scrollHeight;
  }

  // Run initial loading
  init();
});
