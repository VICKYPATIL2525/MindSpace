// ============================================
// TERMS AND CONDITIONS PAGE - SCROLL LOGIC
// ============================================

const termsContent = document.getElementById('termsContent');
const scrollIndicator = document.getElementById('scrollIndicator');
const agreeCheckbox = document.getElementById('agreeCheckbox');
const checkboxLabel = document.getElementById('checkboxLabel');
const acceptBtn = document.getElementById('acceptBtn');
const declineBtn = document.getElementById('declineBtn');

let hasScrolledToBottom = false;

// ============================================
// SCROLL DETECTION
// ============================================

function checkScroll() {
    const scrollTop = termsContent.scrollTop;
    const scrollHeight = termsContent.scrollHeight;
    const clientHeight = termsContent.clientHeight;

    // Calculate how close to bottom (within 50px)
    const scrolledToBottom = scrollTop + clientHeight >= scrollHeight - 50;

    if (scrolledToBottom && !hasScrolledToBottom) {
        hasScrolledToBottom = true;
        onScrolledToBottom();
    }

    // Update scroll indicator visibility
    if (scrolledToBottom) {
        scrollIndicator.classList.add('hidden');
    } else {
        scrollIndicator.classList.remove('hidden');
    }
}

// ============================================
// WHEN USER SCROLLS TO BOTTOM
// ============================================

function onScrolledToBottom() {
    console.log('User has scrolled to bottom');

    // Enable checkbox
    agreeCheckbox.disabled = false;

    // Update label text
    checkboxLabel.textContent = 'I have read and agree to the terms and conditions';

    // Add a subtle pulse effect to checkbox
    agreeCheckbox.parentElement.style.animation = 'pulse 0.5s ease-out';

    // Show notification
    showNotification('✓ You can now accept the terms');
}

// ============================================
// CHECKBOX CHANGE HANDLER
// ============================================

agreeCheckbox.addEventListener('change', function() {
    if (this.checked) {
        acceptBtn.disabled = false;
        acceptBtn.style.animation = 'pulse 0.5s ease-out';
    } else {
        acceptBtn.disabled = true;
    }
});

// ============================================
// ACCEPT BUTTON - Backend Integration Point
// ============================================

acceptBtn.addEventListener('click', async () => {
    if (!hasScrolledToBottom || !agreeCheckbox.checked) {
        showNotification('Please scroll to the bottom and check the box first', 'error');
        return;
    }

    console.log('Terms accepted!');

    // TODO: Backend - Save terms acceptance
    /*
    Example backend integration:

    try {
        const response = await fetch('/api/user/terms/accept', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${localStorage.getItem('token')}`
            },
            body: JSON.stringify({
                acceptedAt: new Date().toISOString(),
                version: '1.0',
                ipAddress: await getClientIP()
            })
        });

        const data = await response.json();

        if (response.ok) {
            // Save acceptance to localStorage
            localStorage.setItem('termsAccepted', 'true');
            localStorage.setItem('termsAcceptedDate', new Date().toISOString());

            // Redirect to next page (dashboard, onboarding, etc.)
            window.location.href = '/dashboard';
        } else {
            showNotification(data.message || 'Failed to save acceptance', 'error');
        }
    } catch (error) {
        console.error('Terms acceptance error:', error);
        showNotification('Network error. Please try again.', 'error');
    }
    */

    // For now - save to localStorage and show alert
    localStorage.setItem('termsAccepted', 'true');
    localStorage.setItem('termsAcceptedDate', new Date().toISOString());

    showNotification('Terms accepted! Redirecting...', 'success');

    // Simulate redirect after 1.5 seconds
    setTimeout(() => {
        alert('Terms accepted successfully!\n\nBackend integration needed:\n- Save acceptance to database\n- Log acceptance timestamp\n- Redirect to next page\n\nSee TODO in script.js');
        // window.location.href = '/dashboard';
    }, 1500);
});

// ============================================
// DECLINE BUTTON - Backend Integration Point
// ============================================

declineBtn.addEventListener('click', () => {
    console.log('Terms declined');

    // Show confirmation dialog
    const confirmed = confirm('Are you sure you want to decline the terms?\n\nYou will not be able to use the service without accepting the terms and conditions.');

    if (confirmed) {
        // TODO: Backend - Log decline and redirect
        /*
        Example backend integration:

        try {
            await fetch('/api/user/terms/decline', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${localStorage.getItem('token')}`
                },
                body: JSON.stringify({
                    declinedAt: new Date().toISOString()
                })
            });

            // Redirect to logout or home page
            window.location.href = '/logout';
        } catch (error) {
            console.error('Terms decline error:', error);
        }
        */

        localStorage.setItem('termsAccepted', 'false');
        alert('Terms declined.\n\nBackend integration needed:\n- Log decline\n- Redirect to logout/home\n\nSee TODO in script.js');
        // window.location.href = '/logout';
    }
});

// ============================================
// SCROLL EVENT LISTENER
// ============================================

termsContent.addEventListener('scroll', checkScroll);

// ============================================
// CHECK ON PAGE LOAD
// ============================================

window.addEventListener('load', () => {
    // Check if user has already accepted terms
    const termsAccepted = localStorage.getItem('termsAccepted');

    if (termsAccepted === 'true') {
        // User has already accepted - optionally redirect
        const acceptedDate = localStorage.getItem('termsAcceptedDate');
        console.log('Terms already accepted on:', acceptedDate);

        // Optionally auto-redirect
        // window.location.href = '/dashboard';
    }

    // Initial scroll check
    checkScroll();

    // Add keyboard shortcut (End key to scroll to bottom)
    document.addEventListener('keydown', (e) => {
        if (e.key === 'End') {
            e.preventDefault();
            termsContent.scrollTop = termsContent.scrollHeight;
        }
    });
});

// ============================================
// NOTIFICATION SYSTEM
// ============================================

function showNotification(message, type = 'info') {
    // Remove existing notification if any
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

    // Add styles dynamically
    const styles = `
        .notification {
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 16px 24px;
            border-radius: 12px;
            font-size: 14px;
            font-weight: 500;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
            animation: slideIn 0.3s ease-out;
            z-index: 1000;
            max-width: 300px;
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

    // Add styles to document if not already added
    if (!document.querySelector('#notification-styles')) {
        const styleSheet = document.createElement('style');
        styleSheet.id = 'notification-styles';
        styleSheet.textContent = styles;
        document.head.appendChild(styleSheet);
    }

    // Auto remove after 3 seconds
    setTimeout(() => {
        notification.style.animation = 'slideOut 0.3s ease-out';
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

// ============================================
// UTILITY FUNCTIONS
// ============================================

// Add pulse animation
const pulseStyle = document.createElement('style');
pulseStyle.textContent = `
    @keyframes pulse {
        0% { transform: scale(1); }
        50% { transform: scale(1.05); }
        100% { transform: scale(1); }
    }
`;
document.head.appendChild(pulseStyle);

// ============================================
// API DOCUMENTATION
// ============================================

/*
RECOMMENDED API ENDPOINTS:

1. POST /api/user/terms/accept
   Request:
   {
       "acceptedAt": "2026-01-30T10:30:00Z",
       "version": "1.0",
       "ipAddress": "192.168.1.1"
   }

   Success Response (200):
   {
       "success": true,
       "message": "Terms acceptance recorded",
       "data": {
           "userId": "user-id",
           "acceptedAt": "2026-01-30T10:30:00Z",
           "version": "1.0"
       }
   }

2. POST /api/user/terms/decline
   Request:
   {
       "declinedAt": "2026-01-30T10:30:00Z"
   }

   Success Response (200):
   {
       "success": true,
       "message": "Decline recorded"
   }

3. GET /api/user/terms/status
   - Check if user has accepted terms
   - Returns acceptance status and date

IMPORTANT NOTES:
- Store acceptance in database with timestamp
- Log IP address for legal compliance
- Version the terms (update version when terms change)
- Require re-acceptance when terms version changes
- Comply with data retention policies
*/

console.log('Terms and Conditions page loaded');
console.log('Scroll to bottom to enable acceptance');
console.log('Check TODO comments for backend integration');
