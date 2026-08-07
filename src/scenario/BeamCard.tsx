// src/scenario/BeamCard.tsx
// v1.0.4: 深色卡片 #1a1a2e + BorderBeam 1.3 dark theme 白色光带强对比
// 之前 (v1.0.3): 浅米色 #FAF7F0 + light theme → 黑色 stroke 0.12 在浅色背景上几乎不可见
// 现在 (v1.0.4): 深紫蓝 #1a1a2e + dark theme → 白色 stroke 0.12 + bloom 0.24 在深色卡上明显
// (跟 BorderBeam 1.3 README quick start 风格一致: <div style={{ background: '#1d1d1d' }}>)
import { BorderBeam } from 'border-beam';
import type { ReactNode } from 'react';

interface BeamCardProps {
  title: string;
  section: 'tree' | 'growth' | 'revenue' | 'commission';
  children: ReactNode;
  colorVariant?: 'colorful' | 'mono' | 'ocean' | 'sunset';
  borderRadius?: number;
  duration?: number;
}

export function BeamCard({
  title, section, children,
  colorVariant = 'colorful', borderRadius = 12, duration = 3.0,
}: BeamCardProps) {
  return (
    <BorderBeam
      size="md"
      colorVariant={colorVariant}
      theme="dark"     /* 深色卡片用 dark: 白色 stroke 0.75 max + bloom 0.85, 在深色卡上强对比 */
      duration={duration}
      borderRadius={borderRadius}
      strength={1.0}   /* 整体强度 max */
      brightness={1.5} /* 1.5x 提亮, 不至于刺眼 */
      className={`beam-wrap beam-wrap-${section}`}
    >
      <div className="beam-content">
        <h3>{title}</h3>
        {children}
      </div>
    </BorderBeam>
  );
}
