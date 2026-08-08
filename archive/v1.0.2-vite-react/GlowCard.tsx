// src/scenario/GlowCard.tsx
// v1.0.5: 纯 CSS conic-gradient 旋转光带, 替换 BorderBeam 1.3
// BorderBeam 1.3 问题: 30% 弧段 + mask 三层 → opacity 0.12-0.26, 肉眼几乎不可见
// 纯 CSS 方案: 外层 conic-gradient 旋转 + 内层遮盖 → 边缘强光带, 100% 可控
import type { ReactNode } from 'react';

interface GlowCardProps {
  title?: string;
  highlight?: boolean;       // TOTAL 卡片用青白色强光
  compact?: boolean;         // 8 报酬小卡片用紧凑模式
  children: ReactNode;
}

export function GlowCard({ title, highlight = false, compact = false, children }: GlowCardProps) {
  return (
    <div className={`glow-card ${highlight ? 'glow-card-highlight' : ''} ${compact ? 'glow-card-compact' : ''}`}>
      <div className="glow-border" />
      <div className="glow-inner">
        {title && <h3>{title}</h3>}
        {children}
      </div>
    </div>
  );
}
