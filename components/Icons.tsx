// components/Icons.tsx
import React from 'react';

interface IconProps extends React.SVGProps<SVGSVGElement> {}

export const LogoIcon: React.FC<IconProps> = (props) => (
  // Simple placeholder book icon
  <svg {...props} xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
  <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.253v13m0-13C10.865 5.39 9.246 5 7.5 5S4.135 5.39 3 6.253v13C4.135 20.11 5.754 20.5 7.5 20.5s3.365-.39 4.5-1.253m0-13C13.135 5.39 14.754 5 16.5 5c1.747 0 3.365.39 4.5 1.253v13C19.865 20.11 18.247 20.5 16.5 20.5c-1.746 0-3.365-.39-4.5-1.253" />
  </svg>
);

export const ChevronRightIcon: React.FC<IconProps> = (props) => (
  <svg {...props} xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
  <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
  </svg>
);
