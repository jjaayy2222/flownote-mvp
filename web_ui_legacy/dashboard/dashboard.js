// ============================================
// FlowNote Dashboard - JavaScript
// ============================================

// Sample Data
const dashboardData = {
    files: [
        {
            file_id: "uuid-001",
            filename: "project_flownote.md",
            para_category: "Projects",
            confidence: 0.95,
            keywords: ["project", "implementation", "objectives"],
            extracted_topics: ["backend development", "api design", "database schema"],
            file_type: "markdown",
            status: "processed"
        },
        {
            file_id: "uuid-002",
            filename: "area_development.md",
            para_category: "Areas",
            confidence: 0.92,
            keywords: ["area", "infrastructure", "maintenance"],
            extracted_topics: ["system maintenance", "infrastructure management"],
            file_type: "markdown",
            status: "processed"
        },
        {
            file_id: "uuid-003",
            filename: "resource_docs.md",
            para_category: "Resources",
            confidence: 0.90,
            keywords: ["resource", "documentation", "reference"],
            extracted_topics: ["technical documentation", "api reference"],
            file_type: "markdown",
            status: "processed"
        },
        {
            file_id: "uuid-004",
            filename: "archive_old.md",
            para_category: "Archives",
            confidence: 0.88,
            keywords: ["archive", "old", "deprecated"],
            extracted_topics: ["legacy system", "historical records"],
            file_type: "markdown",
            status: "processed"
        }
    ]
};

let currentSort = { column: 0, ascending: true };
let filteredData = [...dashboardData.files];

// ============================================
// Initialization
// ============================================
document.addEventListener('DOMContentLoaded', function() {
    console.log('✅ DOM Content Loaded - Initializing dashboard...');
    init();
});

function init() {
    console.log('✅ Initializing with', dashboardData.files.length, 'files');
    filteredData = [...dashboardData.files]; // 초기 데이터 설정
    renderTable(filteredData);
    setupSearch();
    setupFilter();
}

// ============================================
// Table Functions
// ============================================
function renderTable(data) {
    console.log('📊 Rendering table with', data.length, 'files');
    const tbody = document.getElementById('tableBody');
    
    if (!tbody) {
        console.error('❌ Table body element not found!');
        return;
    }
    
    if (data.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; padding: 40px; color: #999;">No files match your criteria</td></tr>';
        return;
    }
    
    tbody.innerHTML = data.map(file => {
        const categoryLower = file.para_category.toLowerCase();
        const confidencePercent = (file.confidence * 100).toFixed(0);
        
        return `
        <tr>
            <td>${escapeHtml(file.filename)}</td>
            <td>
                <span class="badge ${categoryLower}">
                    ${file.para_category}
                </span>
            </td>
            <td>
                <div class="confidence-display">
                    <div class="confidence-bar-small">
                        <div class="confidence-fill ${categoryLower}" 
                             style="width: ${confidencePercent}%;"></div>
                    </div>
                    <span>${confidencePercent}%</span>
                </div>
            </td>
            <td>
                <div class="keywords-display">
                    ${file.keywords.slice(0, 3).map(k => `<span class="keyword-chip">${escapeHtml(k)}</span>`).join('')}
                    ${file.keywords.length > 3 ? `<span class="keyword-chip">+${file.keywords.length - 3}</span>` : ''}
                </div>
            </td>
            <td>
                <span class="status-icon">✅</span>
            </td>
        </tr>
        `;
    }).join('');
    
    console.log('✅ Table rendered successfully with', data.length, 'rows');
}

// ============================================
// Search & Filter Functions
// ============================================
function setupSearch() {
    const searchBox = document.getElementById('searchBox');
    if (!searchBox) {
        console.error('❌ Search box not found!');
        return;
    }
    
    // input 이벤트 사용 (keyup 대신)
    searchBox.addEventListener('input', function(e) {
        console.log('🔍 Search input:', e.target.value);
        applyFilters();
    });
    
    console.log('✅ Search box initialized');
}

function setupFilter() {
    const categoryFilter = document.getElementById('categoryFilter');
    if (!categoryFilter) {
        console.error('❌ Category filter not found!');
        return;
    }
    
    categoryFilter.addEventListener('change', function(e) {
        console.log('🎯 Category filter changed:', e.target.value);
        applyFilters();
    });
    
    console.log('✅ Category filter initialized');
}

function applyFilters() {
    const searchBox = document.getElementById('searchBox');
    const categoryFilter = document.getElementById('categoryFilter');
    
    if (!searchBox || !categoryFilter) {
        console.error('❌ Filter elements not found');
        return;
    }
    
    const searchTerm = searchBox.value.toLowerCase().trim();
    const category = categoryFilter.value;
    
    console.log('🔍 Applying filters - Search:', searchTerm, '| Category:', category);
    
    filteredData = dashboardData.files.filter(file => {
        const matchesSearch = !searchTerm || 
            file.filename.toLowerCase().includes(searchTerm) ||
            file.keywords.some(k => k.toLowerCase().includes(searchTerm));
        
        const matchesCategory = !category || file.para_category === category;
        
        return matchesSearch && matchesCategory;
    });
    
    console.log('✅ Filtered to', filteredData.length, 'files');
    renderTable(filteredData);
}

function clearFilters() {
    console.log('🧹 Clearing all filters');
    
    const searchBox = document.getElementById('searchBox');
    const categoryFilter = document.getElementById('categoryFilter');
    
    if (searchBox) searchBox.value = '';
    if (categoryFilter) categoryFilter.value = '';
    
    filteredData = [...dashboardData.files];
    renderTable(filteredData);
    
    console.log('✅ Filters cleared, showing all', filteredData.length, 'files');
}

// ============================================
// Sort Functions
// ============================================
function sortTable(columnIndex) {
    if (currentSort.column === columnIndex) {
        currentSort.ascending = !currentSort.ascending;
    } else {
        currentSort.column = columnIndex;
        currentSort.ascending = true;
    }
    
    console.log('📊 Sorting column', columnIndex, 'ascending:', currentSort.ascending);
    
    filteredData.sort((a, b) => {
        let aVal, bVal;
        
        switch(columnIndex) {
            case 0:
                aVal = a.filename.toLowerCase();
                bVal = b.filename.toLowerCase();
                break;
            case 1:
                aVal = a.para_category.toLowerCase();
                bVal = b.para_category.toLowerCase();
                break;
            case 2:
                aVal = a.confidence;
                bVal = b.confidence;
                break;
            default:
                return 0;
        }
        
        if (typeof aVal === 'string') {
            return currentSort.ascending 
                ? aVal.localeCompare(bVal)
                : bVal.localeCompare(aVal);
        } else {
            return currentSort.ascending ? aVal - bVal : bVal - aVal;
        }
    });
    
    renderTable(filteredData);
}

// ============================================
// Utility Functions
// ============================================
function escapeHtml(text) {
    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    };
    return String(text).replace(/[&<>"']/g, m => map[m]);
}

// ============================================
// Debug Info
// ============================================
console.log('📝 Dashboard script loaded successfully');
console.log('📊 Total files in data:', dashboardData.files.length);