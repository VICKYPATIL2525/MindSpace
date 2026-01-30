// ============================================
// CLIENT INFORMATION FORM
// ============================================

const form = document.getElementById('infoForm');
const submitBtn = document.getElementById('submitBtn');

// ============================================
// INITIALIZE
// ============================================

function init() {
    // Load saved data if available
    loadSavedData();

    // Add real-time validation
    addValidationListeners();

    // Add auto-save on input
    addAutoSaveListeners();

    // Pin code lookup functionality
    setupPinCodeLookup();

    // Age calculation from DOB
    setupDOBCalculation();

    console.log('Client information form initialized');
}

// ============================================
// LOAD SAVED DATA
// ============================================

function loadSavedData() {
    const savedData = localStorage.getItem('clientInformation');

    if (savedData) {
        try {
            const data = JSON.parse(savedData);

            // Populate form fields
            Object.keys(data).forEach(key => {
                const input = form.querySelector(`[name="${key}"]`);

                if (input) {
                    if (input.type === 'radio' || input.type === 'checkbox') {
                        if (Array.isArray(data[key])) {
                            // Multiple values (checkboxes)
                            data[key].forEach(value => {
                                const checkbox = form.querySelector(`[name="${key}"][value="${value}"]`);
                                if (checkbox) checkbox.checked = true;
                            });
                        } else {
                            // Single value (radio)
                            const radio = form.querySelector(`[name="${key}"][value="${data[key]}"]`);
                            if (radio) radio.checked = true;
                        }
                    } else {
                        input.value = data[key];
                    }
                }
            });

            showNotification('Previous data restored', 'info');
            console.log('Loaded saved data:', data);
        } catch (error) {
            console.error('Failed to load saved data:', error);
        }
    }
}

// ============================================
// AUTO-SAVE
// ============================================

function addAutoSaveListeners() {
    const inputs = form.querySelectorAll('input, select, textarea');

    inputs.forEach(input => {
        input.addEventListener('change', () => {
            saveFormData();
        });

        // Also save on blur for text inputs
        if (input.type === 'text' || input.type === 'email' || input.type === 'tel') {
            input.addEventListener('blur', () => {
                saveFormData();
            });
        }
    });
}

function saveFormData() {
    const formData = new FormData(form);
    const data = {};

    // Handle regular inputs
    for (let [key, value] of formData.entries()) {
        if (data[key]) {
            // Multiple values (checkboxes)
            if (!Array.isArray(data[key])) {
                data[key] = [data[key]];
            }
            data[key].push(value);
        } else {
            data[key] = value;
        }
    }

    localStorage.setItem('clientInformation', JSON.stringify(data));
    console.log('Form data auto-saved');
}

// ============================================
// VALIDATION
// ============================================

function addValidationListeners() {
    const inputs = form.querySelectorAll('input[required]');

    inputs.forEach(input => {
        input.addEventListener('blur', () => {
            validateInput(input);
        });

        input.addEventListener('input', () => {
            if (input.classList.contains('has-error')) {
                validateInput(input);
            }
        });
    });
}

function validateInput(input) {
    const formGroup = input.closest('.form-group');

    if (!input.validity.valid) {
        formGroup.classList.add('has-error');
        showInputError(input);
    } else {
        formGroup.classList.remove('has-error');
        removeInputError(input);
    }
}

function showInputError(input) {
    const formGroup = input.closest('.form-group');
    let errorMsg = formGroup.querySelector('.error-message');

    if (!errorMsg) {
        errorMsg = document.createElement('span');
        errorMsg.className = 'error-message';
        formGroup.appendChild(errorMsg);
    }

    if (input.validity.valueMissing) {
        errorMsg.textContent = 'This field is required';
    } else if (input.validity.typeMismatch) {
        errorMsg.textContent = 'Please enter a valid ' + input.type;
    } else if (input.validity.patternMismatch) {
        errorMsg.textContent = 'Please match the requested format';
    } else {
        errorMsg.textContent = 'Invalid input';
    }
}

function removeInputError(input) {
    const formGroup = input.closest('.form-group');
    const errorMsg = formGroup.querySelector('.error-message');
    if (errorMsg) {
        errorMsg.remove();
    }
}

// ============================================
// PIN CODE LOOKUP
// ============================================

function setupPinCodeLookup() {
    const pinCodeInput = document.getElementById('pinCode');

    pinCodeInput.addEventListener('blur', async () => {
        const pinCode = pinCodeInput.value.trim();

        if (pinCode.length === 6) {
            await lookupPinCode(pinCode);
        }
    });
}

async function lookupPinCode(pinCode) {
    // TODO: Backend - Integrate with Pin Code API
    /*
    Example integration with India Post API:

    try {
        const response = await fetch(`https://api.postalpincode.in/pincode/${pinCode}`);
        const data = await response.json();

        if (data[0].Status === 'Success' && data[0].PostOffice.length > 0) {
            const postOffice = data[0].PostOffice[0];

            // Auto-fill state and district
            document.getElementById('state').value = postOffice.State || '';
            document.getElementById('district').value = postOffice.District || '';
            document.getElementById('address').value = postOffice.Name || '';

            showNotification('Location details auto-filled', 'success');
        } else {
            showNotification('Pin code not found', 'error');
        }
    } catch (error) {
        console.error('Pin code lookup error:', error);
        showNotification('Unable to fetch location details', 'error');
    }
    */

    // For now - just show a message
    console.log('Pin code lookup:', pinCode);
    showNotification('Pin code entered: ' + pinCode, 'info');
}

// ============================================
// DOB TO AGE CALCULATION
// ============================================

function setupDOBCalculation() {
    const dobInput = document.getElementById('dob');
    const ageInput = document.getElementById('age');

    dobInput.addEventListener('change', () => {
        const dob = new Date(dobInput.value);
        const age = calculateAge(dob);

        if (age > 0) {
            ageInput.value = age;
        }
    });

    ageInput.addEventListener('input', () => {
        // Optionally calculate approximate DOB from age
        // Not implemented to avoid conflicts
    });
}

function calculateAge(birthDate) {
    const today = new Date();
    let age = today.getFullYear() - birthDate.getFullYear();
    const monthDiff = today.getMonth() - birthDate.getMonth();

    if (monthDiff < 0 || (monthDiff === 0 && today.getDate() < birthDate.getDate())) {
        age--;
    }

    return age;
}

// ============================================
// FORM SUBMISSION - Backend Integration Point
// ============================================

form.addEventListener('submit', async (event) => {
    event.preventDefault();

    // Validate all required fields
    const requiredInputs = form.querySelectorAll('input[required]');
    let isValid = true;

    requiredInputs.forEach(input => {
        if (!input.validity.valid) {
            validateInput(input);
            isValid = false;
        }
    });

    if (!isValid) {
        showNotification('Please fill all required fields correctly', 'error');

        // Scroll to first error
        const firstError = form.querySelector('.has-error');
        if (firstError) {
            firstError.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
        return;
    }

    // Collect form data
    const formData = new FormData(form);
    const clientData = {};

    // Process form data
    for (let [key, value] of formData.entries()) {
        if (clientData[key]) {
            // Handle multiple values (checkboxes)
            if (!Array.isArray(clientData[key])) {
                clientData[key] = [clientData[key]];
            }
            clientData[key].push(value);
        } else {
            clientData[key] = value;
        }
    }

    console.log('Client Information:', clientData);

    // Disable submit button
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<span>Submitting...</span>';

    // TODO: Backend - Submit client information
    /*
    Example backend integration:

    try {
        const response = await fetch('/api/client/information', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${localStorage.getItem('token')}`
            },
            body: JSON.stringify({
                ...clientData,
                submittedAt: new Date().toISOString(),
                sessionId: localStorage.getItem('sessionId')
            })
        });

        const data = await response.json();

        if (response.ok) {
            // Save client ID
            localStorage.setItem('clientId', data.clientId);

            // Clear saved form data
            localStorage.removeItem('clientInformation');

            showNotification('Information saved successfully!', 'success');

            // Redirect to screening page
            setTimeout(() => {
                window.location.href = '/screening/depression';
            }, 1500);
        } else {
            showNotification(data.message || 'Failed to save information', 'error');
            submitBtn.disabled = false;
            submitBtn.innerHTML = '<span>Submit and Continue</span><svg>...</svg>';
        }
    } catch (error) {
        console.error('Submission error:', error);
        showNotification('Network error. Please try again.', 'error');
        submitBtn.disabled = false;
        submitBtn.innerHTML = '<span>Submit and Continue</span><svg>...</svg>';
    }
    */

    // For now - simulate submission
    setTimeout(() => {
        showNotification('Information submitted successfully!', 'success');

        setTimeout(() => {
            alert(
                'Client Information Submitted!\n\n' +
                'Data collected:\n' +
                `- Name: ${clientData.firstName} ${clientData.lastName}\n` +
                `- Email: ${clientData.email}\n` +
                `- Location: ${clientData.address}, ${clientData.state}\n` +
                `- Age: ${clientData.age}\n\n` +
                'Backend integration needed:\n' +
                '- Save to database with encryption\n' +
                '- Validate data integrity\n' +
                '- Generate client ID\n' +
                '- Redirect to screening assessment\n\n' +
                'See TODO in script.js'
            );

            // Clear saved data
            localStorage.removeItem('clientInformation');

            // Re-enable button
            submitBtn.disabled = false;
            submitBtn.innerHTML = '<span>Submit and Continue</span><svg width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="M5 12h14M12 5l7 7-7 7" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';

            // Redirect simulation
            // window.location.href = '/screening/depression';
        }, 1000);
    }, 2000);
});

// ============================================
// NOTIFICATION SYSTEM
// ============================================

function showNotification(message, type = 'info') {
    const existing = document.querySelector('.notification');
    if (existing) {
        existing.remove();
    }

    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;

    const icon = getNotificationIcon(type);
    notification.innerHTML = `
        ${icon}
        <span>${message}</span>
    `;

    document.body.appendChild(notification);

    if (!document.querySelector('#notification-styles')) {
        const styleSheet = document.createElement('style');
        styleSheet.id = 'notification-styles';
        styleSheet.textContent = `
            .notification {
                position: fixed;
                top: 20px;
                right: 20px;
                padding: 16px 24px;
                border-radius: 12px;
                font-size: 14px;
                font-weight: 500;
                box-shadow: 0 10px 30px rgba(0, 0, 0, 0.15);
                animation: slideIn 0.3s ease-out;
                z-index: 1000;
                max-width: 350px;
                display: flex;
                align-items: center;
                gap: 12px;
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

    setTimeout(() => {
        notification.style.animation = 'slideOut 0.3s ease-out';
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

function getNotificationIcon(type) {
    const icons = {
        success: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><polyline points="22 4 12 14.01 9 11.01" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
        error: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><line x1="15" y1="9" x2="9" y2="15" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><line x1="9" y1="9" x2="15" y2="15" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
        info: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><line x1="12" y1="16" x2="12" y2="12" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><line x1="12" y1="8" x2="12.01" y2="8" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>'
    };
    return icons[type] || icons.info;
}

// ============================================
// KEYBOARD SHORTCUTS
// ============================================

document.addEventListener('keydown', (event) => {
    // Ctrl/Cmd + Enter to submit
    if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
        event.preventDefault();
        form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
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

1. POST /api/client/information
   Request:
   {
       "firstName": "string",
       "lastName": "string",
       "age": 25,
       "dob": "1999-01-30",
       "email": "email@example.com",
       "mobile": "+91-9786543210",
       "maritalStatus": "married",
       "address": "Mumbai",
       "pinCode": "400001",
       "state": "Maharashtra",
       "district": "Mumbai",
       "job": "Software Engineer",
       "company": "Tech Corp",
       "stressReason": ["job-pressure", "financial-problem"],
       "familyMembers": {
           "father": "Name",
           "mother": "Name",
           "spouse": "Name",
           "children": "Names",
           "grandfather": "Name",
           "grandmother": "Name",
           "sister": "Name",
           "brother": "Name"
       },
       "submittedAt": "2026-01-30T10:30:00Z",
       "sessionId": "session-uuid"
   }

   Success Response (200):
   {
       "success": true,
       "clientId": "client-uuid",
       "message": "Information saved successfully",
       "nextStep": "/screening/depression"
   }

2. GET /api/pincode/:pincode
   - Lookup pin code for state/district auto-fill
   - Returns location details

3. GET /api/client/information/:id
   - Retrieve saved client information
   - For editing or review

4. PUT /api/client/information/:id
   - Update client information
   - For corrections or updates

DATA VALIDATION:
- All personal fields must be validated server-side
- Email format validation
- Mobile number format (Indian: +91-XXXXXXXXXX)
- Pin code: 6 digits
- Age: 1-120 years
- DOB: Valid date in past

SECURITY REQUIREMENTS:
- Encrypt sensitive data (PII) at rest
- Use HTTPS for all transmissions
- Implement rate limiting
- Sanitize all inputs
- Store audit logs for data access
- Comply with DPDP Act 2023

IMPORTANT NOTES:
- Family member fields are optional
- Stress reasons can be multiple
- Auto-save progress in case of interruption
- Validate email uniqueness if required
- Generate unique client ID
- Link to user account if authenticated
*/

console.log('Client information form script loaded');
console.log('Form data auto-saves on change');
