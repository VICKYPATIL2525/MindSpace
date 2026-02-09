// MindSpace Integrated Management System - JavaScript

document.addEventListener('DOMContentLoaded', function() {
    initializeNavigation();
    initializeSearch();
    initializeTableInteractivity();
    initializeSortDropdown();
    initializeNoteForm();
    initializeNoteDeletion();
    initializeSettingsMenu();
    initializeFormActions();
    initializeToggleSwitches();
    initializeButtons();
});

/* ========== Navigation ========== */
function initializeNavigation() {
    const navItems = document.querySelectorAll('.nav-item');
    const sections = document.querySelectorAll('.content-section');

    navItems.forEach(item => {
        item.addEventListener('click', function(e) {
            e.preventDefault();

            // Remove active from all nav items and sections
            navItems.forEach(navItem => navItem.classList.remove('active'));
            sections.forEach(section => {
                section.classList.remove('active');
                section.style.display = 'none';
            });

            // Add active to clicked item and corresponding section
            this.classList.add('active');
            const sectionId = this.getAttribute('data-section');
            const targetSection = document.getElementById(sectionId);
            if (targetSection) {
                targetSection.classList.add('active');
                targetSection.style.display = 'block';
            }
        });
    });
}

/* ========== Search Functionality ========== */
function initializeSearch() {
    // Search in tables
    const tableSearchInputs = document.querySelectorAll('.table-controls .search-input');
    tableSearchInputs.forEach(input => {
        input.addEventListener('input', function(e) {
            const searchTerm = e.target.value.toLowerCase();
            const table = this.closest('.table-container').querySelector('.data-table');

            if (table) {
                const tableRows = table.querySelectorAll('tbody tr');
                tableRows.forEach(row => {
                    const text = row.textContent.toLowerCase();
                    row.style.display = text.includes(searchTerm) ? '' : 'none';
                });
            }
        });
    });

    // Search in notes
    const notesSearch = document.querySelector('.notes-container .search-input');
    if (notesSearch) {
        notesSearch.addEventListener('input', function(e) {
            const searchTerm = e.target.value.toLowerCase();
            const noteCards = document.querySelectorAll('.note-card');

            noteCards.forEach(card => {
                const title = card.querySelector('.note-header h3').textContent.toLowerCase();
                const content = card.querySelector('.note-content').textContent.toLowerCase();
                const tag = card.querySelector('.note-tag').textContent.toLowerCase();

                const matches = title.includes(searchTerm) || content.includes(searchTerm) || tag.includes(searchTerm);
                card.style.display = matches ? '' : 'none';
            });
        });
    }

    // Top bar search
    const topBarSearch = document.querySelector('.top-bar .search-input');
    if (topBarSearch) {
        topBarSearch.addEventListener('input', function(e) {
            const searchTerm = e.target.value.toLowerCase();
            const activeSection = document.querySelector('.content-section.active');

            if (activeSection) {
                const table = activeSection.querySelector('.data-table');
                if (table) {
                    const rows = table.querySelectorAll('tbody tr');
                    rows.forEach(row => {
                        const text = row.textContent.toLowerCase();
                        row.style.display = text.includes(searchTerm) ? '' : 'none';
                    });
                }
            }
        });
    }
}

/* ========== Table Interactivity ========== */
function initializeTableInteractivity() {
    const tables = document.querySelectorAll('.data-table');

    tables.forEach(table => {
        const tableRows = table.querySelectorAll('tbody tr');
        tableRows.forEach(row => {
            row.addEventListener('click', function() {
                tableRows.forEach(r => r.style.backgroundColor = '');
                this.style.backgroundColor = '#f0f4ff';
            });
        });
    });
}

/* ========== Sort Dropdown ========== */
function initializeSortDropdown() {
    const sortDropdowns = document.querySelectorAll('.sort-dropdown');

    sortDropdowns.forEach(dropdown => {
        dropdown.addEventListener('change', function(e) {
            if (e.target.value === 'Name A-Z' || e.target.value === 'Z-A') {
                sortTable(this, 0);
            } else if (e.target.value === 'Date') {
                sortTable(this, 2);
            } else if (e.target.value === 'Recent') {
                console.log('Sort by recent');
            }
        });
    });
}

function sortTable(dropdownElement, column) {
    const table = dropdownElement.closest('.table-container') ?
                  dropdownElement.closest('.table-container').querySelector('.data-table') :
                  dropdownElement.closest('.table-controls').querySelector('.data-table');

    if (!table) return;

    const tbody = table.querySelector('tbody');
    const rows = Array.from(tbody.querySelectorAll('tr'));

    rows.sort((a, b) => {
        const aValue = a.children[column].textContent.trim();
        const bValue = b.children[column].textContent.trim();

        const aNum = parseFloat(aValue);
        const bNum = parseFloat(bValue);

        if (!isNaN(aNum) && !isNaN(bNum)) {
            return aNum - bNum;
        }
        return aValue.localeCompare(bValue);
    });

    rows.forEach(row => tbody.appendChild(row));
}

/* ========== Initialize Buttons ========== */
function initializeButtons() {
    // Add Counsellor Button
    const addCounsellorBtn = document.querySelector('.btn-add-counsellor');
    if (addCounsellorBtn) {
        addCounsellorBtn.addEventListener('click', function() {
            alert('Add New Counsellor modal would open here');
        });
    }

    // Add Client Button
    const addClientBtn = document.querySelector('.btn-add-client');
    if (addClientBtn) {
        addClientBtn.addEventListener('click', function() {
            alert('Add New Client modal would open here');
        });
    }

    // Search Button
    const searchBtn = document.querySelector('.btn-search');
    if (searchBtn) {
        searchBtn.addEventListener('click', function() {
            alert('Search functionality triggered');
        });
    }

    // View Logs Button
    const logButtons = document.querySelectorAll('.btn-view-logs');
    logButtons.forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.stopPropagation();
            alert('View logs modal would open here');
        });
    });
}

/* ========== Notes Form ========== */
function initializeNoteForm() {
    const addNoteBtn = document.querySelector('.btn-add-note');
    const addNoteForm = document.getElementById('addNoteForm');
    const saveNoteBtn = document.querySelector('.btn-save-note');
    const cancelNoteBtn = document.querySelector('.btn-cancel-note');
    const notesGrid = document.getElementById('notesGrid');
    const noteTitleInput = document.getElementById('noteTitle');
    const noteContentInput = document.getElementById('noteContent');

    if (addNoteBtn) {
        addNoteBtn.addEventListener('click', function() {
            if (addNoteForm) {
                addNoteForm.style.display = addNoteForm.style.display === 'none' ? 'block' : 'none';
                if (addNoteForm.style.display === 'block') {
                    noteTitleInput.focus();
                }
            }
        });
    }

    if (cancelNoteBtn) {
        cancelNoteBtn.addEventListener('click', function() {
            addNoteForm.style.display = 'none';
            noteTitleInput.value = '';
            noteContentInput.value = '';
        });
    }

    if (saveNoteBtn) {
        saveNoteBtn.addEventListener('click', function() {
            const title = noteTitleInput.value.trim();
            const content = noteContentInput.value.trim();

            if (title === '' || content === '') {
                alert('Please enter both title and content');
                return;
            }

            const newNote = createNoteElement(title, content);
            notesGrid.insertBefore(newNote, notesGrid.firstChild);

            noteTitleInput.value = '';
            noteContentInput.value = '';
            addNoteForm.style.display = 'none';

            initializeNoteDeletion();
        });
    }
}

function createNoteElement(title, content) {
    const today = new Date();
    const dateStr = today.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });

    const noteCard = document.createElement('div');
    noteCard.className = 'note-card';
    noteCard.innerHTML = `
        <div class="note-header">
            <h3>${escapeHtml(title)}</h3>
            <button class="note-delete-btn">×</button>
        </div>
        <p class="note-content">${escapeHtml(content)}</p>
        <p class="note-date">${dateStr}</p>
        <span class="note-tag">New</span>
    `;

    return noteCard;
}

/* ========== Notes Deletion ========== */
function initializeNoteDeletion() {
    const deleteButtons = document.querySelectorAll('.note-delete-btn');

    deleteButtons.forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.stopPropagation();
            const noteCard = this.closest('.note-card');
            noteCard.style.opacity = '0';
            noteCard.style.transform = 'scale(0.95)';
            setTimeout(() => {
                noteCard.remove();
            }, 300);
        });
    });
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/* ========== Settings Menu ========== */
function initializeSettingsMenu() {
    const menuItems = document.querySelectorAll('.settings-menu-item');
    const sections = document.querySelectorAll('.settings-section-content');

    menuItems.forEach(item => {
        item.addEventListener('click', function() {
            const sectionId = this.getAttribute('data-settings-section');

            // Remove active class from all menu items and sections
            menuItems.forEach(menuItem => menuItem.classList.remove('active'));
            sections.forEach(section => {
                section.classList.remove('active');
                section.style.display = 'none';
            });

            // Add active class to clicked item and corresponding section
            this.classList.add('active');
            const targetSection = document.getElementById(sectionId + '-content');
            if (targetSection) {
                targetSection.classList.add('active');
                targetSection.style.display = 'block';
            }
        });
    });
}

/* ========== Form Actions ========== */
function initializeFormActions() {
    const saveButtons = document.querySelectorAll('.btn-save');

    saveButtons.forEach(btn => {
        btn.addEventListener('click', function() {
            alert('Settings saved successfully!');
        });
    });

    const secondaryButtons = document.querySelectorAll('.btn-secondary');
    secondaryButtons.forEach(btn => {
        btn.addEventListener('click', function() {
            const buttonText = this.textContent.trim();
            alert(buttonText + ' would be triggered here');
        });
    });
}

/* ========== Toggle Switches ========== */
function initializeToggleSwitches() {
    const toggles = document.querySelectorAll('.toggle-switch input');

    toggles.forEach(toggle => {
        toggle.addEventListener('change', function() {
            const label = this.closest('.notification-header') ?
                          this.closest('.notification-header').querySelector('h3').textContent :
                          'Setting';
            const state = this.checked ? 'enabled' : 'disabled';
            console.log(label + ' ' + state);
        });
    });
}
