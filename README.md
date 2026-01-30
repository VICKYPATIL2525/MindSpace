# MindSpace - Mental Health Screening Platform

A complete web application for mental health screening and assessment, built with vanilla HTML, CSS, and JavaScript.

## 📋 Project Overview

MindSpace is a mental health screening platform that guides users through a structured assessment process. The application collects user information, obtains consent, and conducts mental health screenings (depression, anxiety, ADHD, etc.).

## 🗂️ Project Structure

```
figma-mcp-test/
├── mindspace-landing-page/     # Homepage - Entry point
├── signup-page/                # User registration
├── auth-pages/
│   ├── login-page/            # User login
│   └── language-page/         # Language selection
├── terms-page/                # Terms & conditions with scroll-to-accept
├── user-info-page/            # Client information form
└── screening-page/            # Mental health assessment questions
```

## 🔄 User Flow

```
1. Landing Page (mindspace-landing-page/)
   ↓ Click "Get Started"

2. Sign Up Page (signup-page/)
   ↓ New user registration

3. Login Page (auth-pages/login-page/)
   ↓ User authentication

4. Language Selection (auth-pages/language-page/)
   ↓ Choose preferred language

5. Terms & Conditions (terms-page/)
   ↓ Scroll to bottom → Accept terms

6. User Information (user-info-page/)
   ↓ Fill personal & family details

7. Screening Questions (screening-page/)
   ↓ Answer depression assessment

8. [Continue to other assessments...]
```

## 📁 Folder Details

### 1. **mindspace-landing-page/**
- Homepage with hero section, features, testimonials
- Call-to-action: "Get Started" button → links to signup

### 2. **signup-page/**
- New user registration form
- Fields: Name, Email, Password
- Social signup options (Google, Apple)
- Link to login page

### 3. **auth-pages/login-page/**
- User login form
- Email & password fields
- Remember me checkbox
- Password visibility toggle
- Social login options

### 4. **auth-pages/language-page/**
- Language selection (8 languages available)
- Hindi, English, Bengali, Telugu, Marathi, Tamil, Gujarati, Kannada
- Shows native scripts
- Browser language auto-detection

### 5. **terms-page/**
- Scrollable terms and conditions
- Checkbox disabled until user scrolls to bottom
- Accept button enabled only after checkbox checked
- Stores acceptance in localStorage

### 6. **user-info-page/**
- Comprehensive client information form
- Sections:
  - Personal Information (name, age, DOB, email, mobile)
  - Address Details (city, pin code, state, district)
  - Professional Information (job, company)
  - Stress Factors (multiple selection)
  - Family Members (optional)
- Auto-save functionality
- Real-time validation

### 7. **screening-page/**
- Mental health screening questionnaire
- Depression assessment (4 questions)
- 0-3 scale for each question
- Progress indicator
- Score calculation
- Continue button disabled until all answered

## 🔧 Technical Stack

- **Frontend**: Pure HTML5, CSS3, JavaScript (ES6+)
- **Fonts**: Inter (Google Fonts)
- **Storage**: LocalStorage for session persistence
- **Responsive**: Mobile-first design
- **Accessibility**: Keyboard navigation, ARIA labels, focus states

## 🚀 Setup & Running

Each folder is self-contained with `index.html`, `styles.css`, and `script.js`.



## 🔌 Backend Integration

All pages have backend integration points marked with `// TODO: Backend` comments.

### Key API Endpoints Needed:

```
POST   /api/auth/signup           - User registration
POST   /api/auth/login            - User authentication
POST   /api/user/terms/accept     - Save terms acceptance
POST   /api/client/information    - Save client details
POST   /api/screening/depression  - Submit screening results
GET    /api/pincode/:pincode      - Location lookup
```

### Data Flow:

1. User signs up → Get auth token
2. User logs in → Store token in localStorage
3. All subsequent API calls include token in headers:
   ```javascript
   headers: {
       'Authorization': `Bearer ${localStorage.getItem('token')}`
   }
   ```

## 📊 Data Storage

### LocalStorage Keys Used:

- `token` - Authentication token
- `userId` - User ID
- `sessionId` - Session identifier
- `selectedLanguage` - Chosen language
- `termsAccepted` - Terms acceptance status
- `termsAcceptedDate` - Acceptance timestamp
- `clientInformation` - Form auto-save data
- `depressionScreening` - Screening answers

## 🎨 Design System

### Colors:
- Primary: `#8fb9a8` (Sage Green)
- Secondary: `#a7c7e7` (Light Blue)
- Background: `#f6f9f8` (Off White)
- Text: `#2e3a3a` (Dark Gray)

### Typography:
- Font Family: Inter
- Headings: 600-700 weight
- Body: 400-500 weight

## ✅ Features Implemented

- ✅ Responsive design (mobile, tablet, desktop)
- ✅ Form validation (client-side)
- ✅ Auto-save functionality
- ✅ Progress tracking
- ✅ Keyboard shortcuts
- ✅ Accessibility features
- ✅ Loading states
- ✅ Error handling
- ✅ Success notifications
- ✅ Session persistence

## 🔐 Security Considerations

- All forms include CSRF protection placeholders
- Password fields have visibility toggle
- Email validation
- Input sanitization needed on backend
- HTTPS required for production
- Sensitive data encrypted at rest
- Compliance with DPDP Act 2023

## 📱 Browser Support

- Chrome (latest)
- Firefox (latest)
- Safari (latest)
- Edge (latest)
- Mobile browsers (iOS Safari, Chrome Mobile)

## 🐛 Known Limitations

- Backend APIs need implementation
- Email verification not included
- Password reset flow not included
- Multi-language content not translated (UI only)
- No real-time validation against database

## 👨‍💻 Development Notes

- All code is well-commented
- Each page is independent (no shared dependencies)
- No build process required
- No npm packages needed
- Pure vanilla JavaScript (no frameworks)

## 📝 Next Steps for Backend Developer

1. Set up API endpoints (see Backend Integration section)
2. Implement authentication (JWT recommended)
3. Set up database schema for:
   - Users
   - Client Information
   - Screening Results
   - Terms Acceptance Logs
4. Add email verification
5. Implement password reset
6. Set up pin code lookup API
7. Add multi-language content translation
8. Deploy frontend to CDN/static hosting
9. Deploy backend to server
10. Configure CORS and security headers

## 📄 License

Proprietary - MindSpace Mental Health Platform

## 👥 Contact

For questions or support, contact the development team.

---

**Note**: All TODO comments in the code indicate backend integration points. Search for `// TODO: Backend` to find all integration locations.
