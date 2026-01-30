// Smooth scroll for anchor links
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
        e.preventDefault();
        const target = document.querySelector(this.getAttribute('href'));
        if (target) {
            target.scrollIntoView({ behavior: 'smooth' });
        }
    });
});

// Newsletter form submission
const emailInput = document.getElementById('emailInput');
const sendButton = document.getElementById('sendButton');

if (sendButton && emailInput) {
    sendButton.addEventListener('click', (e) => {
        e.preventDefault();
        const email = emailInput.value.trim();

        if (email && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
            alert(`Thank you for subscribing! We'll send updates to ${email}`);
            emailInput.value = '';
        } else {
            alert('Please enter a valid email address.');
        }
    });

    // Allow Enter key to submit
    emailInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            sendButton.click();
        }
    });
}

// Header scroll effect
const header = document.querySelector('.header');
let lastScroll = 0;

window.addEventListener('scroll', () => {
    const currentScroll = window.pageYOffset;

    if (currentScroll > 100) {
        header.style.background = 'rgba(13, 13, 13, 0.95)';
        header.style.backdropFilter = 'blur(10px)';
        header.style.transition = 'all 0.3s';
    } else {
        header.style.background = 'transparent';
    }

    lastScroll = currentScroll;
});
