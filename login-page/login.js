// ============================================
// LOGIN PAGE JAVASCRIPT
// ============================================

// Password Toggle Functionality
const togglePassword = document.getElementById('togglePassword');
const passwordInput = document.getElementById('password');
const eyeIcon = togglePassword.querySelector('.eye-icon');
const eyeOffIcon = togglePassword.querySelector('.eye-off-icon');

togglePassword.addEventListener('click', () => {
    const type = passwordInput.getAttribute('type') === 'password' ? 'text' : 'password';
    passwordInput.setAttribute('type', type);

    eyeIcon.classList.toggle('hidden');
    eyeOffIcon.classList.toggle('hidden');
});

// ============================================
// FORM SUBMISSION - Backend Integration Point
// ============================================

document.getElementById('loginForm').addEventListener('submit', async (e) => {
    e.preventDefault();

    // Get form data
    const formData = {
        email: document.getElementById('email').value.trim(),
        password: document.getElementById('password').value,
        remember: document.getElementById('remember').checked
    };

    console.log('Login Data:', formData);

    // TODO: Backend - API call to login endpoint
    /*
    Example backend integration:

    try {
        const response = await fetch('/api/auth/login', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                email: formData.email,
                password: formData.password
            })
        });

        const data = await response.json();

        if (response.ok) {
            // Success - store token
            if (formData.remember) {
                localStorage.setItem('token', data.token);
                localStorage.setItem('refreshToken', data.refreshToken);
            } else {
                sessionStorage.setItem('token', data.token);
            }

            // Redirect to dashboard
            window.location.href = '/dashboard';
        } else {
            // Show error message
            showError(data.message || 'Login failed');
        }
    } catch (error) {
        console.error('Login error:', error);
        showError('Network error. Please try again.');
    }
    */

    // Temporary alert
    alert('Login submitted!\n\nEmail: ' + formData.email + '\nRemember: ' + formData.remember + '\n\nBackend integration needed - see TODO in login.js');
});

// ============================================
// FORGOT PASSWORD - Backend Integration Point
// ============================================

document.getElementById('forgotPassword').addEventListener('click', () => {
    const email = document.getElementById('email').value.trim();

    console.log('Forgot password clicked for:', email);

    // TODO: Backend - Navigate to forgot password page or show modal
    /*
    Example backend integration:

    if (email) {
        // Send reset email directly
        try {
            await fetch('/api/auth/forgot-password', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email })
            });
            showSuccess('Password reset link sent to your email');
        } catch (error) {
            showError('Failed to send reset link');
        }
    } else {
        // Navigate to forgot password page
        window.location.href = '/forgot-password';
    }
    */

    if (email) {
        alert('Password reset link will be sent to:\n' + email + '\n\nBackend integration needed - see TODO in login.js');
    } else {
        alert('Please enter your email first or navigate to forgot password page\n\nBackend integration needed - see TODO in login.js');
    }
});

// ============================================
// GOOGLE LOGIN - Backend Integration Point
// ============================================

document.getElementById('googleLogin').addEventListener('click', () => {
    console.log('Google login clicked');

    // TODO: Backend - Redirect to Google OAuth
    /*
    Example backend integration:
    window.location.href = '/api/auth/google';

    Backend should:
    1. Redirect to Google OAuth consent screen
    2. Handle callback
    3. Create/login user
    4. Return token
    5. Redirect to dashboard
    */

    alert('Google login clicked!\n\nBackend integration needed - see TODO in login.js');
});

// ============================================
// APPLE LOGIN - Backend Integration Point
// ============================================

document.getElementById('appleLogin').addEventListener('click', () => {
    console.log('Apple login clicked');

    // TODO: Backend - Redirect to Apple OAuth
    /*
    Example backend integration:
    window.location.href = '/api/auth/apple';

    Backend should:
    1. Redirect to Apple OAuth consent screen
    2. Handle callback
    3. Create/login user
    4. Return token
    5. Redirect to dashboard
    */

    alert('Apple login clicked!\n\nBackend integration needed - see TODO in login.js');
});

// ============================================
// SIGN UP NAVIGATION - Backend Integration Point
// ============================================

document.getElementById('signupLink').addEventListener('click', () => {
    console.log('Navigate to Sign Up');

    // TODO: Backend - Navigate to signup page
    /*
    Example backend integration:
    window.location.href = '/signup';
    */

    alert('Navigate to Sign Up page!\n\nBackend integration needed - see TODO in login.js');
});

// ============================================
// FORM VALIDATION (Enhanced)
// ============================================

// Real-time email validation
document.getElementById('email').addEventListener('blur', function() {
    const email = this.value.trim();
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

    if (email && !emailRegex.test(email)) {
        this.style.borderColor = '#ff4444';
        showError('Please enter a valid email address');
    } else {
        this.style.borderColor = '#a7c7e7';
    }
});

// Password field focus/blur effects
document.getElementById('password').addEventListener('focus', function() {
    this.parentElement.style.borderColor = '#7ab3d6';
});

document.getElementById('password').addEventListener('blur', function() {
    this.parentElement.style.borderColor = '';
});

// ============================================
// UTILITY FUNCTIONS
// ============================================

function showError(message) {
    // TODO: Implement proper error UI (toast, modal, inline message, etc.)
    console.error('Error:', message);
    // For now, using alert - replace with better UI
    // alert(message);
}

function showSuccess(message) {
    // TODO: Implement proper success UI (toast, modal, inline message, etc.)
    console.log('Success:', message);
    // For now, using alert - replace with better UI
    // alert(message);
}

// ============================================
// REMEMBER ME - LocalStorage Management
// ============================================

// Check if user has saved email
window.addEventListener('DOMContentLoaded', () => {
    const savedEmail = localStorage.getItem('rememberedEmail');
    if (savedEmail) {
        document.getElementById('email').value = savedEmail;
        document.getElementById('remember').checked = true;
    }
});

// Save email if remember me is checked
document.getElementById('remember').addEventListener('change', function() {
    if (this.checked) {
        const email = document.getElementById('email').value.trim();
        if (email) {
            localStorage.setItem('rememberedEmail', email);
        }
    } else {
        localStorage.removeItem('rememberedEmail');
    }
});

// ============================================
// API ENDPOINT DOCUMENTATION
// ============================================

/*
RECOMMENDED API ENDPOINTS:

1. POST /api/auth/login
   Request:
   {
       "email": "user@example.com",
       "password": "SecurePass123!"
   }

   Success Response (200):
   {
       "success": true,
       "message": "Login successful",
       "data": {
           "userId": "unique-user-id",
           "email": "user@example.com",
           "name": "John Doe",
           "token": "jwt-token",
           "refreshToken": "refresh-token"
       }
   }

   Error Response (401):
   {
       "success": false,
       "message": "Invalid email or password"
   }

2. POST /api/auth/forgot-password
   Request:
   {
       "email": "user@example.com"
   }

   Success Response (200):
   {
       "success": true,
       "message": "Password reset link sent to your email"
   }

3. GET /api/auth/google
   - Redirects to Google OAuth
   - Callback: /api/auth/google/callback

4. GET /api/auth/apple
   - Redirects to Apple OAuth
   - Callback: /api/auth/apple/callback
*/

console.log('Login page loaded - Ready for backend integration!');
console.log('Check TODO comments for integration points');
