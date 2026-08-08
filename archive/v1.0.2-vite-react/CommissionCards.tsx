// src/scenario/CommissionCards.tsx
// v1.0.5: 8 种报酬卡片, 用 GlowCard 包裹 (纯 CSS 旋转光带)
import { GlowCard } from './GlowCard';
import type { Overview } from './types';

const FIELDS: { key: keyof Overview; label: string; highlight?: boolean }[] = [
  { key: 'ownBasic', label: 'ownBasic' },
  { key: 'pairBonus', label: 'pairBonus' },
  { key: 'teamBonus', label: 'teamBonus' },
  { key: 'savings', label: 'savings' },
  { key: 'leader', label: 'leader' },
  { key: 'horizontal', label: 'horizontal' },
  { key: 'retail', label: 'retail' },
  { key: 'total', label: 'total', highlight: true },
];

function formatUSD(raw: string | number | undefined): string {
  const n = parseFloat(String(raw ?? '0'));
  if (isNaN(n)) return '$0.00';
  return '$' + n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

interface CommissionCardsProps {
  overview: Overview | null;
}

export function CommissionCards({ overview }: CommissionCardsProps) {
  return (
    <div className="p3-cards">
      {FIELDS.map(({ key, label, highlight }) => (
        <GlowCard key={key} highlight={highlight} compact>
          <div className="label">{label}</div>
          <div className="val">
            {overview ? formatUSD(overview[key]) : '—'}
          </div>
        </GlowCard>
      ))}
    </div>
  );
}
