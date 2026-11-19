// Global type declarations
/// <reference types="vite/client" />

declare module 'recharts' {
  export * from 'recharts/types';
}

declare module '@tanstack/react-query-devtools' {
  export const ReactQueryDevtools: React.FC<{ initialIsOpen?: boolean; position?: string; className?: string }>;
  export const ReactQueryDevtoolsPanel: React.FC<any>;
  export type DevtoolsPanelOptions = any;
}

declare module 'react-chartjs-2' {
  export * from 'react-chartjs-2/dist/index.esm.js';
}

// Fix for recharts types
declare namespace JSX {
  interface IntrinsicElements {
    'recharts-wrapper': React.DetailedHTMLProps<React.HTMLAttributes<HTMLElement>, HTMLElement>;
  }
}