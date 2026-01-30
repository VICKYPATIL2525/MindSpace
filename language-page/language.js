// ============================================
// LANGUAGE SELECTION PAGE JAVASCRIPT
// ============================================

let selectedLanguage = null;

// Get all language cards
const languageCards = document.querySelectorAll('.language-card');
const continueBtn = document.getElementById('continueBtn');

// ============================================
// LANGUAGE SELECTION LOGIC
// ============================================

languageCards.forEach(card => {
    card.addEventListener('click', function() {
        // Remove selected class from all cards
        languageCards.forEach(c => c.classList.remove('selected'));

        // Add selected class to clicked card
        this.classList.add('selected');

        // Store selected language
        selectedLanguage = this.getAttribute('data-lang');

        // Enable continue button
        continueBtn.disabled = false;

        // Add selection animation
        this.style.animation = 'none';
        setTimeout(() => {
            this.style.animation = 'pulse 0.3s ease-out';
        }, 10);

        console.log('Selected language:', selectedLanguage);
    });

    // Add keyboard support
    card.addEventListener('keypress', function(e) {
        if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            this.click();
        }
    });
});

// ============================================
// CONTINUE BUTTON - Backend Integration Point
// ============================================

continueBtn.addEventListener('click', async () => {
    if (!selectedLanguage) {
        alert('Please select a language first');
        return;
    }

    console.log('Continue with language:', selectedLanguage);

    // TODO: Backend - Save language preference
    /*
    Example backend integration:

    try {
        // Save language preference to backend
        const response = await fetch('/api/user/language', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${localStorage.getItem('token')}`
            },
            body: JSON.stringify({
                language: selectedLanguage
            })
        });

        const data = await response.json();

        if (response.ok) {
            // Save to localStorage for client-side use
            localStorage.setItem('preferredLanguage', selectedLanguage);

            // Load language translations
            await loadLanguageTranslations(selectedLanguage);

            // Redirect to next page (dashboard, onboarding, etc.)
            window.location.href = '/dashboard';
        } else {
            showError(data.message || 'Failed to save language preference');
        }
    } catch (error) {
        console.error('Language save error:', error);
        showError('Network error. Please try again.');
    }
    */

    // For now - save to localStorage and show alert
    localStorage.setItem('preferredLanguage', selectedLanguage);

    alert('Language selected: ' + selectedLanguage + '\n\nBackend integration needed:\n- Save preference to user profile\n- Load appropriate translations\n- Redirect to next page\n\nSee TODO in language.js');
});

// ============================================
// LANGUAGE PERSISTENCE
// ============================================

// Check if user has previously selected a language
window.addEventListener('DOMContentLoaded', () => {
    const savedLanguage = localStorage.getItem('preferredLanguage');

    if (savedLanguage) {
        // Pre-select the saved language
        const savedCard = document.querySelector(`[data-lang="${savedLanguage}"]`);
        if (savedCard) {
            savedCard.click();
        }
    } else {
        // Auto-detect browser language and select if available
        const browserLang = navigator.language.split('-')[0]; // e.g., 'en' from 'en-US'
        const browserCard = document.querySelector(`[data-lang="${browserLang}"]`);
        if (browserCard) {
            // Don't auto-click, just highlight as suggested
            browserCard.style.borderColor = '#a4c4b5';
            browserCard.style.borderWidth = '2px';
        }
    }
});

// ============================================
// LANGUAGE TRANSLATIONS LOADER
// ============================================

async function loadLanguageTranslations(langCode) {
    // TODO: Backend - Load translation file
    /*
    Example backend integration:

    try {
        const response = await fetch(`/api/i18n/${langCode}.json`);
        const translations = await response.json();

        // Store translations globally
        window.translations = translations;

        // Apply translations to current page
        applyTranslations();

        return translations;
    } catch (error) {
        console.error('Failed to load translations:', error);
        // Fallback to English
        return await loadLanguageTranslations('en');
    }
    */

    console.log('Load translations for:', langCode);
}

// ============================================
// KEYBOARD NAVIGATION ENHANCEMENT
// ============================================

let currentIndex = 0;

document.addEventListener('keydown', (e) => {
    const cards = Array.from(languageCards);

    switch(e.key) {
        case 'ArrowRight':
            e.preventDefault();
            currentIndex = (currentIndex + 1) % cards.length;
            cards[currentIndex].focus();
            break;

        case 'ArrowLeft':
            e.preventDefault();
            currentIndex = (currentIndex - 1 + cards.length) % cards.length;
            cards[currentIndex].focus();
            break;

        case 'ArrowDown':
            e.preventDefault();
            currentIndex = Math.min(currentIndex + 4, cards.length - 1);
            cards[currentIndex].focus();
            break;

        case 'ArrowUp':
            e.preventDefault();
            currentIndex = Math.max(currentIndex - 4, 0);
            cards[currentIndex].focus();
            break;

        case 'Enter':
            if (document.activeElement.classList.contains('language-card')) {
                document.activeElement.click();
            } else if (document.activeElement === continueBtn && !continueBtn.disabled) {
                continueBtn.click();
            }
            break;
    }
});

// ============================================
// SKIP LANGUAGE SELECTION (Optional)
// ============================================

// If you want to add a "Skip for now" option
function addSkipOption() {
    const skipBtn = document.createElement('button');
    skipBtn.textContent = 'Skip for now';
    skipBtn.className = 'link-button';
    skipBtn.style.marginTop = '16px';

    skipBtn.addEventListener('click', () => {
        // TODO: Backend - Skip language selection
        console.log('Skip language selection');

        // Set default language (English)
        localStorage.setItem('preferredLanguage', 'en');

        // Redirect to next page
        // window.location.href = '/dashboard';

        alert('Skipped - Default language (English) set\n\nBackend integration needed - see TODO in language.js');
    });

    document.querySelector('.language-footer').appendChild(skipBtn);
}

// Uncomment to enable skip option
// addSkipOption();

// ============================================
// UTILITY FUNCTIONS
// ============================================

function showError(message) {
    console.error('Error:', message);
    // TODO: Implement proper error UI
}

// Add pulse animation for selection feedback
const style = document.createElement('style');
style.textContent = `
    @keyframes pulse {
        0% { transform: scale(1); }
        50% { transform: scale(1.05); }
        100% { transform: scale(1); }
    }
`;
document.head.appendChild(style);

// ============================================
// API ENDPOINT DOCUMENTATION
// ============================================

/*
RECOMMENDED API ENDPOINTS:

1. POST /api/user/language
   Request:
   {
       "language": "hi"
   }

   Success Response (200):
   {
       "success": true,
       "message": "Language preference saved",
       "data": {
           "language": "hi",
           "languageName": "Hindi"
       }
   }

2. GET /api/i18n/{langCode}.json
   - Returns translation file for specified language
   - Example: /api/i18n/hi.json

   Response:
   {
       "welcome": "स्वागत",
       "login": "लॉग इन करें",
       "signup": "साइन अप करें",
       ...
   }

3. GET /api/user/profile
   - Include language preference in user profile
   - Returns user data including preferred language

LANGUAGE CODES:
- en: English
- hi: Hindi (हिन्दी)
- mr: Marathi (मराठी)
- bn: Bengali (বাংলা)
- ta: Tamil (தமிழ்)
- te: Telugu (తెలుగు)
- gu: Gujarati (ગુજરાતી)
- kn: Kannada (ಕನ್ನಡ)
*/

console.log('Language selection page loaded - Ready for backend integration!');
console.log('Check TODO comments for integration points');
