// ============================================
// MENTAL HEALTH SCREENING - DEPRESSION ASSESSMENT
// ============================================

const form = document.getElementById('screeningForm');
const continueBtn = document.getElementById('continueBtn');
const backBtn = document.getElementById('backBtn');
const answeredCountEl = document.getElementById('answeredCount');
const totalCountEl = document.getElementById('totalCount');
const progressFillEl = document.getElementById('progressFill');

// Track answers
const totalQuestions = 4;
let answeredQuestions = new Set();

// ============================================
// INITIALIZE
// ============================================

function init() {
    // Set total count
    totalCountEl.textContent = totalQuestions;

    // Load saved answers from localStorage if available
    loadSavedAnswers();

    // Add event listeners to all radio buttons
    const radioButtons = form.querySelectorAll('input[type="radio"]');
    radioButtons.forEach(radio => {
        radio.addEventListener('change', handleAnswerChange);
    });

    // Initial validation check
    validateForm();

    console.log('Screening page initialized');
}

// ============================================
// LOAD SAVED ANSWERS
// ============================================

function loadSavedAnswers() {
    const savedData = localStorage.getItem('depressionScreening');

    if (savedData) {
        try {
            const answers = JSON.parse(savedData);

            // Restore radio selections
            Object.keys(answers).forEach(questionName => {
                const value = answers[questionName];
                const radio = form.querySelector(`input[name="${questionName}"][value="${value}"]`);
                if (radio) {
                    radio.checked = true;
                    answeredQuestions.add(questionName);

                    // Add answered class to question block
                    const questionBlock = radio.closest('.question-block');
                    if (questionBlock) {
                        questionBlock.classList.add('answered');
                    }
                }
            });

            console.log('Loaded saved answers:', answers);
            updateProgress();
        } catch (error) {
            console.error('Failed to load saved answers:', error);
        }
    }
}

// ============================================
// HANDLE ANSWER CHANGE
// ============================================

function handleAnswerChange(event) {
    const input = event.target;
    const questionName = input.name;

    // Mark question as answered
    answeredQuestions.add(questionName);

    // Add visual feedback
    const questionBlock = input.closest('.question-block');
    if (questionBlock && !questionBlock.classList.contains('answered')) {
        questionBlock.classList.add('answered');
    }

    // Update progress
    updateProgress();

    // Validate form
    validateForm();

    // Save answers to localStorage
    saveAnswers();

    console.log(`Question ${questionName} answered with value: ${input.value}`);
}

// ============================================
// UPDATE PROGRESS
// ============================================

function updateProgress() {
    const count = answeredQuestions.size;
    const percentage = (count / totalQuestions) * 100;

    // Update count text
    answeredCountEl.textContent = count;

    // Update progress bar
    progressFillEl.style.width = `${percentage}%`;

    // Add completion feedback
    if (count === totalQuestions) {
        progressFillEl.style.background = 'linear-gradient(90deg, #10b981 0%, #34d399 100%)';
        showNotification('All questions answered! You can now continue.', 'success');
    }
}

// ============================================
// VALIDATE FORM
// ============================================

function validateForm() {
    const allAnswered = answeredQuestions.size === totalQuestions;

    // Enable/disable continue button
    continueBtn.disabled = !allAnswered;

    return allAnswered;
}

// ============================================
// SAVE ANSWERS
// ============================================

function saveAnswers() {
    const formData = new FormData(form);
    const answers = {};

    for (let [key, value] of formData.entries()) {
        answers[key] = value;
    }

    localStorage.setItem('depressionScreening', JSON.stringify(answers));
    console.log('Answers saved to localStorage');
}

// ============================================
// CALCULATE SCORE
// ============================================

function calculateScore() {
    const formData = new FormData(form);
    let totalScore = 0;

    for (let value of formData.values()) {
        totalScore += parseInt(value);
    }

    return totalScore;
}

// ============================================
// FORM SUBMISSION - Backend Integration Point
// ============================================

form.addEventListener('submit', async (event) => {
    event.preventDefault();

    if (!validateForm()) {
        showNotification('Please answer all questions before continuing', 'error');
        return;
    }

    // Calculate score
    const score = calculateScore();
    const formData = new FormData(form);
    const answers = {};

    for (let [key, value] of formData.entries()) {
        answers[key] = parseInt(value);
    }

    console.log('Depression Assessment Results:');
    console.log('Answers:', answers);
    console.log('Total Score:', score);

    // TODO: Backend - Submit screening results
    /*
    Example backend integration:

    try {
        const response = await fetch('/api/screening/depression', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${localStorage.getItem('token')}`
            },
            body: JSON.stringify({
                category: 'depression',
                answers: answers,
                totalScore: score,
                completedAt: new Date().toISOString(),
                sessionId: localStorage.getItem('sessionId')
            })
        });

        const data = await response.json();

        if (response.ok) {
            // Save screening ID
            localStorage.setItem('depressionScreeningId', data.screeningId);

            // Redirect to next section (anxiety, ADHD, etc.)
            window.location.href = '/screening/anxiety';
        } else {
            showNotification(data.message || 'Failed to save results', 'error');
        }
    } catch (error) {
        console.error('Screening submission error:', error);
        showNotification('Network error. Please try again.', 'error');
    }
    */

    // For now - show results and simulate redirect
    showNotification('Assessment submitted successfully!', 'success');

    setTimeout(() => {
        alert(
            `Depression Screening Complete!\n\n` +
            `Total Score: ${score}/12\n\n` +
            `Interpretation:\n` +
            `0-3: Minimal symptoms\n` +
            `4-6: Mild symptoms\n` +
            `7-9: Moderate symptoms\n` +
            `10-12: Severe symptoms\n\n` +
            `Backend integration needed:\n` +
            `- Save screening results to database\n` +
            `- Calculate risk level\n` +
            `- Generate recommendations\n` +
            `- Proceed to next screening section\n\n` +
            `See TODO in script.js`
        );

        // window.location.href = '/screening/anxiety';
    }, 1000);
});

// ============================================
// BACK BUTTON
// ============================================

backBtn.addEventListener('click', () => {
    console.log('Back button clicked');

    // Confirm if user wants to go back
    const hasAnswers = answeredQuestions.size > 0;

    if (hasAnswers) {
        const confirmed = confirm(
            'Your answers have been saved.\n\n' +
            'Do you want to go back to the previous page?'
        );

        if (confirmed) {
            // TODO: Backend - Navigate to previous page
            // window.location.href = '/screening/intro';

            alert('Backend integration needed:\n- Navigate to previous page\n\nSee TODO in script.js');
        }
    } else {
        // TODO: Backend - Navigate to previous page
        // window.location.href = '/screening/intro';

        alert('Backend integration needed:\n- Navigate to previous page\n\nSee TODO in script.js');
    }
});

// ============================================
// NOTIFICATION SYSTEM
// ============================================

function showNotification(message, type = 'info') {
    // Remove existing notification
    const existing = document.querySelector('.notification');
    if (existing) {
        existing.remove();
    }

    // Create notification
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.textContent = message;

    // Add to page
    document.body.appendChild(notification);

    // Add styles if not already added
    if (!document.querySelector('#notification-styles')) {
        const styleSheet = document.createElement('style');
        styleSheet.id = 'notification-styles';
        styleSheet.textContent = `
            .notification {
                position: fixed;
                top: 80px;
                right: 20px;
                padding: 16px 24px;
                border-radius: 8px;
                font-size: 14px;
                font-weight: 500;
                box-shadow: 0 10px 30px rgba(0, 0, 0, 0.15);
                animation: slideIn 0.3s ease-out;
                z-index: 1000;
                max-width: 350px;
            }

            .notification-success {
                background: #10b981;
                color: white;
            }

            .notification-error {
                background: #ef4444;
                color: white;
            }

            .notification-info {
                background: #3b82f6;
                color: white;
            }

            @keyframes slideIn {
                from {
                    transform: translateX(400px);
                    opacity: 0;
                }
                to {
                    transform: translateX(0);
                    opacity: 1;
                }
            }

            @keyframes slideOut {
                from {
                    transform: translateX(0);
                    opacity: 1;
                }
                to {
                    transform: translateX(400px);
                    opacity: 0;
                }
            }
        `;
        document.head.appendChild(styleSheet);
    }

    // Auto remove after 3 seconds
    setTimeout(() => {
        notification.style.animation = 'slideOut 0.3s ease-out';
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

// ============================================
// AUTO-SAVE ON PAGE UNLOAD
// ============================================

window.addEventListener('beforeunload', (event) => {
    if (answeredQuestions.size > 0 && answeredQuestions.size < totalQuestions) {
        saveAnswers();

        // Show warning if form is incomplete
        event.preventDefault();
        event.returnValue = 'You have unanswered questions. Your progress has been saved.';
    }
});

// ============================================
// KEYBOARD SHORTCUTS
// ============================================

document.addEventListener('keydown', (event) => {
    // Press Enter on Continue button if all questions answered
    if (event.key === 'Enter' && !continueBtn.disabled && document.activeElement !== continueBtn) {
        event.preventDefault();
        continueBtn.click();
    }

    // Press Escape to go back
    if (event.key === 'Escape') {
        backBtn.click();
    }

    // Number keys 0-3 to select options for focused question
    if (['0', '1', '2', '3'].includes(event.key)) {
        const focusedOption = document.activeElement.closest('.option');
        if (focusedOption) {
            const questionBlock = focusedOption.closest('.question-block');
            const options = questionBlock.querySelectorAll('input[type="radio"]');
            const index = parseInt(event.key);

            if (options[index]) {
                options[index].checked = true;
                options[index].dispatchEvent(new Event('change', { bubbles: true }));
            }
        }
    }
});

// ============================================
// INITIALIZE ON PAGE LOAD
// ============================================

window.addEventListener('load', init);

// ============================================
// API DOCUMENTATION
// ============================================

/*
RECOMMENDED API ENDPOINTS:

1. POST /api/screening/depression
   Request:
   {
       "category": "depression",
       "answers": {
           "q1": 0,
           "q2": 1,
           "q3": 2,
           "q4": 1
       },
       "totalScore": 4,
       "completedAt": "2026-01-30T10:30:00Z",
       "sessionId": "session-uuid"
   }

   Success Response (200):
   {
       "success": true,
       "screeningId": "screening-uuid",
       "score": 4,
       "riskLevel": "mild",
       "recommendations": [
           "Consider regular physical activity",
           "Maintain consistent sleep schedule",
           "Connect with friends and family"
       ],
       "nextSection": "/screening/anxiety"
   }

2. GET /api/screening/depression/status
   - Check if user has completed depression screening
   - Returns completion status and last saved answers

3. PUT /api/screening/depression/:id
   - Update existing screening answers
   - Allow users to modify their responses

4. GET /api/screening/progress
   - Get overall screening progress across all categories
   - Returns completed sections and next recommended section

SCORING GUIDELINES:
- Each question scored 0-3
- Total score range: 0-12
- Interpretation:
  * 0-3: Minimal symptoms
  * 4-6: Mild symptoms
  * 7-9: Moderate symptoms
  * 10-12: Severe symptoms

IMPORTANT NOTES:
- Save progress automatically as user answers
- Allow users to navigate back and forth between sections
- Validate all inputs before submission
- Store screening timestamp for longitudinal tracking
- Ensure data privacy and encryption
- Comply with mental health data regulations
*/

console.log('Screening page script loaded');
console.log('Answer questions to enable the Continue button');
