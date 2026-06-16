# Mobile UI Redesign: iOS Bottom Bar + Liquid Glass

## Context

The race timing app currently has a desktop-first design with a horizontal top navbar. On mobile, the navbar overflows and the experience is not optimized. The user wants to:

1. Add an iOS-style **bottom navigation bar** for mobile
2. Apply **liquid glass** (iOS 27) visual effects to UI components
3. **Preserve** the existing light/dark theme system

## Approach

Pure CSS + template changes. No new dependencies. Tailwind CDN + existing `theme.css` system.

---

## 1. Bottom Navigation Bar

**Where:** `templates/base.html`

Add a fixed bottom nav bar that is **only visible on mobile** (`< md` breakpoint). The top navbar stays for desktop.

**Bottom nav items (max 4-5 for iOS HIG):**

| Icon | Label | Route | Notes |
|---|---|---|---|
| `flag` | Events | `/` | Always visible |
| `palette` | Colors | `/car-model-colors` | Admin only |
| `users` | Users | `/users` | Admin only |
| `log-in` / `user` | Login/Profile | `/login` or logout | Auth-dependent |

**Implementation:**
- In `base.html`: add `<nav class="bottom-nav">` before `</body>`, hidden on `md:` and up
- Add `padding-bottom: 4.5rem` to body on mobile to prevent content from being hidden behind the bar
- Each item is a link with icon + label, centered, with active state highlighting
- Active state detection: compare `request.path` in Jinja2
- Use `backdrop-filter: blur()` for the glass effect on the bar itself

**Child templates** can override a `{% block bottom_nav_active %}` to set which tab is active (default: "Events").

---

## 2. Liquid Glass Effects

**Where:** `static/css/theme.css`

iOS 27's liquid glass is characterized by:
- **Heavy blur** with `backdrop-filter: blur(20px) saturate(180%)`
- **Translucent surfaces** with low-opacity backgrounds
- **Subtle gradient borders** (not solid lines)
- **Inner glow** via `box-shadow` with inset highlights
- **Smooth rounded corners** (larger radius)
- **Layered depth** — cards float above the background

**CSS changes in `theme.css`:**

### New CSS variables (add to `:root` and `[data-theme="dark"]`):
```css
--glass-blur-heavy: 24px;
--glass-saturate: 180%;
--glass-bg-light: rgba(255, 255, 255, 0.55);
--glass-bg-dark: rgba(17, 24, 39, 0.55);
--glass-border-gradient: linear-gradient(135deg, rgba(255,255,255,0.3), rgba(255,255,255,0.05));
--glass-inner-glow: inset 0 1px 0 rgba(255, 255, 255, 0.15);
--glass-radius: 1rem;
```

### Update existing classes:
- `.card` → add `backdrop-filter: blur(20px) saturate(180%)`, translucent bg, gradient border, inner glow, larger radius
- `.card-glass` → enhance with heavier blur + saturate
- `.nav-main` → heavier blur, gradient border bottom
- `.bottom-nav` → glass effect (new class)
- `.themed-input`, `.themed-select` → glass background on focus
- `.btn-primary`, `.btn-ghost` → subtle glass tint

### New `.liquid-glass` utility class:
```css
.liquid-glass {
    background: var(--glass-bg);
    backdrop-filter: blur(24px) saturate(180%);
    -webkit-backdrop-filter: blur(24px) saturate(180%);
    border: 1px solid var(--glass-border);
    box-shadow: var(--glass-inner-glow), 0 8px 32px rgba(0,0,0,0.1);
    border-radius: var(--glass-radius);
}
```

### Dark mode adjustments:
- Dark mode glass uses darker translucent backgrounds with slightly different blur
- Inner glow becomes `inset 0 1px 0 rgba(255, 255, 255, 0.06)`
- Border is more subtle

---

## 3. Files to Modify

| File | Changes |
|---|---|
| `templates/base.html` | Add bottom nav HTML, add mobile padding-bottom, add `{% block bottom_nav_active %}` |
| `static/css/theme.css` | New glass variables, update `.card`, `.nav-main`, add `.bottom-nav`, `.liquid-glass`, mobile media queries |
| `templates/session_detail.html` | Override `bottom_nav_active` block |
| `templates/event_detail.html` | Override `bottom_nav_active` block |
| `templates/index.html` | Override `bottom_nav_active` block (default, no override needed) |

---

## 4. Detailed Bottom Nav HTML (base.html)

```html
<!-- Bottom Navigation (mobile only) -->
<nav class="bottom-nav fixed bottom-0 left-0 right-0 z-50 md:hidden">
    <div class="flex items-center justify-around h-16 px-2">
        <a href="{{ url_for('main.index') }}" class="bottom-nav-item {% if request.endpoint == 'main.index' %}active{% endif %}">
            <i data-lucide="flag" class="w-5 h-5"></i>
            <span class="text-xs">Events</span>
        </a>
        {% block bottom_nav_extra %}{% endblock %}
        {% if current_user and current_user.is_admin %}
        <a href="{{ url_for('main.car_model_colors') }}" class="bottom-nav-item {% if request.endpoint == 'main.car_model_colors' %}active{% endif %}">
            <i data-lucide="palette" class="w-5 h-5"></i>
            <span class="text-xs">Colors</span>
        </a>
        <a href="{{ url_for('main.user_list') }}" class="bottom-nav-item {% if request.endpoint == 'main.user_list' %}active{% endif %}">
            <i data-lucide="users" class="w-5 h-5"></i>
            <span class="text-xs">Users</span>
        </a>
        {% endif %}
        {% if current_user %}
        <a href="{{ url_for('main.logout') }}" class="bottom-nav-item">
            <i data-lucide="log-out" class="w-5 h-5"></i>
            <span class="text-xs">Logout</span>
        </a>
        {% else %}
        <a href="{{ url_for('main.login') }}" class="bottom-nav-item {% if request.endpoint == 'main.login' %}active{% endif %}">
            <i data-lucide="log-in" class="w-5 h-5"></i>
            <span class="text-xs">Login</span>
        </a>
        {% endif %}
    </div>
</nav>
```

---

## 5. Detailed CSS (theme.css additions)

```css
/* -- Bottom Navigation -- */
.bottom-nav {
    background: var(--glass-bg);
    backdrop-filter: blur(24px) saturate(180%);
    -webkit-backdrop-filter: blur(24px) saturate(180%);
    border-top: 1px solid var(--glass-border);
    box-shadow: 0 -4px 30px rgba(0, 0, 0, 0.1);
    padding-bottom: env(safe-area-inset-bottom, 0);
}

.bottom-nav-item {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.125rem;
    padding: 0.375rem 0.75rem;
    border-radius: 0.5rem;
    color: var(--text-muted);
    text-decoration: none;
    font-size: 0.625rem;
    transition: color 0.2s, background 0.2s;
    -webkit-tap-highlight-color: transparent;
}

.bottom-nav-item:hover,
.bottom-nav-item.active {
    color: var(--accent-cyan);
    background: rgba(0, 229, 255, 0.08);
}

/* -- Liquid Glass Cards -- */
.card {
    background: var(--glass-bg);
    backdrop-filter: blur(20px) saturate(180%);
    -webkit-backdrop-filter: blur(20px) saturate(180%);
    border: 1px solid var(--glass-border);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.12),
                0 4px 24px rgba(0, 0, 0, 0.08);
    border-radius: var(--glass-radius);
}

/* -- Mobile body padding -- */
@media (max-width: 767px) {
    body {
        padding-bottom: 5rem;
    }
}
```

---

## 6. Verification

1. **Desktop** (`>= 768px`): Bottom nav hidden, top navbar visible, cards have glass effect
2. **Mobile** (`< 768px`): Bottom nav visible, top navbar still visible, content padded to avoid bottom bar overlap
3. **Light mode**: Glass surfaces are white-translucent with subtle inner glow
4. **Dark mode**: Glass surfaces are dark-translucent, inner glow is more subtle
5. **Theme toggle**: Switching themes updates glass surfaces correctly (CSS variables handle this)
6. **All pages**: Bottom nav appears on every page (login, events, session detail, etc.)
7. **Safe area**: `env(safe-area-inset-bottom)` handles iPhone notch/home indicator

---

## 7. Risks & Mitigations

- **Performance**: `backdrop-filter` with heavy blur can be slow on older mobile devices. Mitigation: keep blur at 20-24px (not 40px+), saturate at 180% (not 200%+).
- **Safari compatibility**: `-webkit-backdrop-filter` is included for iOS Safari.
- **Content overlap**: `padding-bottom: 5rem` on mobile prevents content from hiding behind the bottom nav.
- **Table horizontal scroll**: Wide tables already use `overflow-x: auto`, no change needed.
