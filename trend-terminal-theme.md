# Trend Terminal — Light Purple Theme (index.css)

```css
@import "tailwindcss";
@import "tw-animate-css";
@plugin "@tailwindcss/typography";

@custom-variant dark (&:is(.dark *));

@theme inline {
  --color-background: hsl(var(--background));
  --color-foreground: hsl(var(--foreground));
  --color-border: hsl(var(--border));
  --color-input: hsl(var(--input));
  --color-ring: hsl(var(--ring));

  --color-card: hsl(var(--card));
  --color-card-foreground: hsl(var(--card-foreground));
  --color-card-border: hsl(var(--card-border));

  --color-popover: hsl(var(--popover));
  --color-popover-foreground: hsl(var(--popover-foreground));
  --color-popover-border: hsl(var(--popover-border));

  --color-primary: hsl(var(--primary));
  --color-primary-foreground: hsl(var(--primary-foreground));
  --color-primary-border: var(--primary-border);

  --color-secondary: hsl(var(--secondary));
  --color-secondary-foreground: hsl(var(--secondary-foreground));
  --color-secondary-border: var(--secondary-border);

  --color-muted: hsl(var(--muted));
  --color-muted-foreground: hsl(var(--muted-foreground));
  --color-muted-border: var(--muted-border);

  --color-accent: hsl(var(--accent));
  --color-accent-foreground: hsl(var(--accent-foreground));
  --color-accent-border: var(--accent-border);

  --color-destructive: hsl(var(--destructive));
  --color-destructive-foreground: hsl(var(--destructive-foreground));
  --color-destructive-border: var(--destructive-border);

  --color-chart-1: hsl(var(--chart-1));
  --color-chart-2: hsl(var(--chart-2));
  --color-chart-3: hsl(var(--chart-3));
  --color-chart-4: hsl(var(--chart-4));
  --color-chart-5: hsl(var(--chart-5));

  --color-sidebar: hsl(var(--sidebar));
  --color-sidebar-foreground: hsl(var(--sidebar-foreground));
  --color-sidebar-border: hsl(var(--sidebar-border));
  --color-sidebar-primary: hsl(var(--sidebar-primary));
  --color-sidebar-primary-foreground: hsl(var(--sidebar-primary-foreground));
  --color-sidebar-primary-border: var(--sidebar-primary-border);
  --color-sidebar-accent: hsl(var(--sidebar-accent));
  --color-sidebar-accent-foreground: hsl(var(--sidebar-accent-foreground));
  --color-sidebar-accent-border: var(--sidebar-accent-border);
  --color-sidebar-ring: hsl(var(--sidebar-ring));

  --font-sans: var(--app-font-sans);
  --font-serif: var(--app-font-serif);
  --font-mono: var(--app-font-mono);

  --text-xs: 0.75rem;
  --text-xs--line-height: calc(1 / 0.75);
  --text-sm: 0.875rem;
  --text-sm--line-height: calc(1.25 / 0.875);
  --text-base: 1rem;
  --text-base--line-height: calc(1.5 / 1);
  --text-lg: 1.125rem;
  --text-lg--line-height: calc(1.75 / 1.125);
  --text-xl: 1.25rem;
  --text-xl--line-height: calc(1.75 / 1.25);
  --text-2xl: 1.5rem;
  --text-2xl--line-height: calc(2 / 1.5);
  --text-3xl: 1.875rem;
  --text-3xl--line-height: calc(2.25 / 1.875);
  --text-4xl: 2.25rem;
  --text-4xl--line-height: calc(2.5 / 2.25);
  --text-5xl: 3rem;
  --text-5xl--line-height: 1;
  --text-6xl: 3.75rem;
  --text-6xl--line-height: 1;
  --text-7xl: 4.5rem;
  --text-7xl--line-height: 1;
  --text-8xl: 6rem;
  --text-8xl--line-height: 1;
  --text-9xl: 8rem;
  --text-9xl--line-height: 1;

  --radius-sm: calc(var(--radius) - 4px);
  --radius-md: calc(var(--radius) - 2px);
  --radius-lg: var(--radius);
  --radius-xl: calc(var(--radius) + 4px);
}

/* Light purple theme — inspired by modern SaaS dashboards */
:root {
  color-scheme: light;
  --button-outline: rgba(124,92,252, 0.08);
  --badge-outline: rgba(124,92,252, 0.04);
  --opaque-button-border-intensity: 6;

  --elevate-1: rgba(124,92,252, 0.04);
  --elevate-2: rgba(124,92,252, 0.08);

  --background: 250 30% 96%;      /* #F5F3FF very light lavender */
  --foreground: 240 10% 18%;      /* #262626 near-black */

  --card: 0 0% 100%;              /* #FFFFFF white */
  --card-foreground: 240 10% 18%;
  --card-border: 250 30% 90%;     /* #E5E0FF light purple border */

  --popover: 0 0% 100%;
  --popover-foreground: 240 10% 18%;
  --popover-border: 250 30% 90%;

  --primary: 258 95% 66%;         /* #7C5CFC vivid purple */
  --primary-foreground: 0 0% 100%;

  --secondary: 250 30% 94%;      /* #F0EEFF lighter lavender */
  --secondary-foreground: 240 10% 18%;

  --muted: 250 20% 94%;
  --muted-foreground: 240 5% 45%;   /* #6B7280 muted gray */

  --accent: 250 30% 94%;
  --accent-foreground: 240 10% 18%;

  --destructive: 0 84% 60%;
  --destructive-foreground: 0 0% 100%;

  --border: 250 30% 90%;
  --input: 250 30% 94%;
  --ring: 258 95% 66%;

  --sidebar: 250 30% 96%;
  --sidebar-foreground: 240 10% 18%;
  --sidebar-border: 250 30% 90%;
  --sidebar-primary: 258 95% 66%;
  --sidebar-primary-foreground: 0 0% 100%;
  --sidebar-accent: 250 30% 94%;
  --sidebar-accent-foreground: 240 10% 18%;
  --sidebar-ring: 258 95% 66%;

  /* Charts — softer palette */
  --chart-1: 258 95% 66%;   /* Purple */
  --chart-2: 0 84% 60%;     /* Red */
  --chart-3: 240 5% 65%;    /* Gray */
  --chart-4: 43 100% 50%;   /* Amber */
  --chart-5: 217 91% 60%;   /* Blue */

  --app-font-sans: 'Inter', ui-sans-serif, system-ui, sans-serif;
  --app-font-serif: Georgia, serif;
  --app-font-mono: 'JetBrains Mono', ui-monospace, monospace;

  --radius: 0.75rem;

  --shadow-2xs: 0 1px 2px 0 rgba(124,92,252,0.04);
  --shadow-xs:  0 1px 2px 0 rgba(124,92,252,0.06);
  --shadow-sm:  0 1px 3px 0 rgba(124,92,252,0.08), 0 1px 2px -1px rgba(124,92,252,0.04);
  --shadow:     0 4px 6px -1px rgba(124,92,252,0.08), 0 2px 4px -2px rgba(124,92,252,0.04);
  --shadow-md:  0 6px 12px -2px rgba(124,92,252,0.08), 0 3px 6px -3px rgba(124,92,252,0.04);
  --shadow-lg:  0 10px 20px -4px rgba(124,92,252,0.10), 0 4px 8px -4px rgba(124,92,252,0.05);
  --shadow-xl:  0 16px 32px -6px rgba(124,92,252,0.12), 0 6px 12px -6px rgba(124,92,252,0.05);
  --shadow-2xl: 0 24px 48px -8px rgba(124,92,252,0.14);

  --tracking-normal: 0em;
  --spacing: 0.25rem;
}

@layer base {
  * {
    @apply border-border;
  }

  body {
    @apply font-sans antialiased bg-background text-foreground;
  }
}
```
