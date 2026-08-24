/**
 * AI-Based Study Assistant — Main JavaScript
 * Handles UI interactions: mobile nav, scroll effects, etc.
 */

document.addEventListener('DOMContentLoaded', () => {

  // ── Navbar scroll effect ────────────────────────────────────────────────
  const navbar = document.getElementById('navbar');
  if (navbar) {
    window.addEventListener('scroll', () => {
      navbar.style.background = window.scrollY > 40
        ? 'hsl(230, 20%, 7%, 0.97)'
        : 'hsl(230, 20%, 7%, 0.75)';
    }, { passive: true });
  }

  // ── Mobile nav toggle ───────────────────────────────────────────────────
  const navToggle = document.getElementById('navToggle');
  const navLinks  = document.querySelector('.nav-links');
  const navActions = document.querySelector('.nav-actions');

  if (navToggle) {
    navToggle.addEventListener('click', () => {
      const isOpen = navLinks.classList.toggle('open');
      navActions?.classList.toggle('open', isOpen);
      navToggle.setAttribute('aria-expanded', isOpen);
    });
  }

  // ── Smooth reveal on scroll (Intersection Observer) ─────────────────────
  const revealEls = document.querySelectorAll('.card, .section-header');
  if (revealEls.length) {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach(entry => {
          if (entry.isIntersecting) {
            entry.target.style.animation = 'fadeInDown .55s ease both';
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.12 }
    );
    revealEls.forEach(el => observer.observe(el));
  }

  // ── Health check (verifies API is reachable) ────────────────────────────
  fetch('/api/health')
    .then(r => r.json())
    .then(data => console.log('[StudyAI] API health:', data))
    .catch(() => console.warn('[StudyAI] API health check failed.'));

});
