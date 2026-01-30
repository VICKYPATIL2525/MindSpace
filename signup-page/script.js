// ============================================
// BACKEND INTEGRATION POINTS
// ============================================

// Handle form submission
document.getElementById('signupForm').addEventListener('submit', async function(e) {
    e.preventDefault();

    // Get form data
    const formData = {
        name: document.getElementById('name').value,
        email: document.getElementById('email').value,
        password: document.getElementById('password').value,
        agreeToTerms: document.getElementById('agreeToTerms').checked
    };

    console.log('Form Data:', formData);

    // TODO: Backend - Send data to API
    /*
    Example backend integration:

    try {
        const response = await fetch('/api/auth/signup', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(formData)
        });

        const data = await response.json();

        if (response.ok) {
            // Success - store token and redirect
            localStorage.setItem('token', data.token);
            window.location.href = '/dashboard';
        } else {
            // Error - show validation messages
            alert(data.message || 'Signup failed');
        }
    } catch (error) {
        console.error('Error:', error);
        alert('Network error. Please try again.');
    }
    */

    // Temporary success message
    alert('Form submitted! Check console for data.\n\nBackend integration needed - see TODO comments in script.js');
});

// Handle Google signup
document.getElementById('googleSignup').addEventListener('click', function() {
    console.log('Google signup clicked');

    // TODO: Backend - Redirect to Google OAuth
    /*
    Example backend integration:
    window.location.href = '/api/auth/google';

    Backend should:
    1. Redirect to Google OAuth consent screen
    2. Handle callback
    3. Create/login user
    4. Return token
    */

    alert('Google signup clicked!\n\nBackend integration needed - see TODO comments in script.js');
});

// Handle Apple signup
document.getElementById('appleSignup').addEventListener('click', function() {
    console.log('Apple signup clicked');

    // TODO: Backend - Redirect to Apple OAuth
    /*
    Example backend integration:
    window.location.href = '/api/auth/apple';

    Backend should:
    1. Redirect to Apple OAuth consent screen
    2. Handle callback
    3. Create/login user
    4. Return token
    */

    alert('Apple signup clicked!\n\nBackend integration needed - see TODO comments in script.js');
});

// Handle Sign In navigation
document.getElementById('signinButton').addEventListener('click', function() {
    console.log('Navigate to Sign In');

    // TODO: Backend - Navigate to signin page
    /*
    Example backend integration:
    window.location.href = '/signin';
    or
    window.location.href = '/login';
    */

    alert('Navigate to Sign In!\n\nBackend integration needed - see TODO comments in script.js');
});

// ============================================
// FORM VALIDATION (Optional Enhancement)
// ============================================

// Real-time email validation
document.getElementById('email').addEventListener('blur', function() {
    const email = this.value;
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

    if (email && !emailRegex.test(email)) {
        this.style.borderColor = '#ff4444';
        console.log('Invalid email format');
    } else {
        this.style.borderColor = '#a7c7e7';
    }
});

// Real-time password strength check
document.getElementById('password').addEventListener('input', function() {
    const password = this.value;

    // TODO: Backend - Implement password strength requirements
    // Example: Minimum 8 chars, 1 uppercase, 1 lowercase, 1 number, 1 special char

    if (password.length < 8) {
        this.style.borderColor = '#ff4444';
        console.log('Password too short');
    } else {
        this.style.borderColor = '#a7c7e7';
    }
});

// ============================================
// API ENDPOINT EXAMPLES FOR BACKEND DEV
// ============================================

/*
RECOMMENDED API ENDPOINTS:

1. POST /api/auth/signup
   Request Body:
   {
       "name": "John Doe",
       "email": "john@example.com",
       "password": "SecurePass123!",
       "agreeToTerms": true
   }

   Success Response (201):
   {
       "success": true,
       "message": "Account created successfully",
       "data": {
           "userId": "unique-user-id",
           "email": "john@example.com",
           "token": "jwt-token-here"
       }
   }

   Error Response (400):
   {
       "success": false,
       "message": "Validation failed",
       "errors": {
           "email": "Email already exists",
           "password": "Password too weak"
       }
   }

2. GET /api/auth/google
   - Redirects to Google OAuth
   - Callback: /api/auth/google/callback

3. GET /api/auth/apple
   - Redirects to Apple OAuth
   - Callback: /api/auth/apple/callback

4. GET /signin or /login
   - Sign in page route
*/

// ============================================
// SECURITY NOTES FOR BACKEND DEVELOPERS
// ============================================

/*
IMPORTANT SECURITY CONSIDERATIONS:

1. Password Hashing
   - Use bcrypt with salt rounds >= 10
   - Never store plain text passwords

2. Input Validation
   - Validate all inputs server-side
   - Sanitize data to prevent XSS/SQL injection

3. Rate Limiting
   - Limit signup attempts (e.g., 5 per 15 minutes)
   - Prevent brute force attacks

4. CORS Configuration
   - Allow only trusted origins
   - Set proper headers

5. JWT Security
   - Use strong secret keys
   - Set appropriate expiration times
   - Consider refresh tokens

6. HTTPS Only
   - Always use HTTPS in production
   - Set secure cookie flags

7. Email Verification
   - Send verification email after signup
   - Verify email before full access
*/

console.log('Sign Up Page Loaded - Ready for Backend Integration!');
console.log('Check TODO comments in script.js for integration points');
