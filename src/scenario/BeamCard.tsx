// src/scenario/BeamCard.tsx
// v1.0.2: 单个 beam-wrap 卡片 (BorderBeam 包裹内容)
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

/**
 * 单个 beam-wrap 卡片, 用 BorderBeam 组件画光带 (size="md" full border 旋转)
 * - size="md"           : full border rotating beam (跟原 CSS .beam-wrap 通道一致)
 * - colorVariant="ocean" : 蓝紫色调, 跟我们青色 teal 主题相近
 * - theme="dark"         : 深色背景适配
 * - duration={2.5}       : 跟原 CSS 方案 2.5s 一致
 * - borderRadius={12}    : 跟 .beam-wrap 圆角一致
 * - strength={0.8}       : 整体强度 80% (光带不会太亮刺眼)
 */
export function BeamCard({
  title, section, children,
  colorVariant = 'ocean', borderRadius = 12, duration = 2.5,
}: BeamCardProps) {
  return (
    <BorderBeam
      size="md"
      colorVariant={colorVariant}
      theme="light"  /* light theme 在深色背景上 stroke 颜色更明显 (深色 stroke 0.2) */
      duration={duration}
      borderRadius={borderRadius}
      strength={1.0}
      brightness={1.5}
      className={`beam-wrap beam-wrap-${section}`}
    >
      <div className="beam-content">
        <h3>{title}</h3>
        {children}
      </div>
    </BorderBeam>
  );
}
