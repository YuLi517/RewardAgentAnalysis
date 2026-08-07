// src/scenario/BeamCard.tsx
// v1.0.3: 浅色背景 + light theme + colorful 色系, 让 BorderBeam 1.3 光带强对比显示
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
 * 单个 beam-wrap 卡片, BorderBeam 1.3 画光带
 * v1.0.3 调强: colorful + light + 强 brightness 配浅米色背景
 * - size="md"              : full border rotating beam
 * - colorVariant="colorful" : 多彩 (青/紫/金/粉) - 在浅色背景上最显眼
 * - theme="light"           : 浅色背景用, stroke=黑色 0.4 + blur 8px + bloom=0.34
 * - duration={3.0}          : 比 v1.0.2 稍慢, 让眼睛跟上
 * - borderRadius={12}       : 跟 .beam-wrap 圆角一致
 * - strength={1.0}          : 全强度
 * - brightness={2.0}        : 提亮 2x, 让浅色背景下黑色 stroke + 多彩 bloom 都明显
 */
export function BeamCard({
  title, section, children,
  colorVariant = 'colorful', borderRadius = 12, duration = 3.0,
}: BeamCardProps) {
  return (
    <BorderBeam
      size="md"
      colorVariant={colorVariant}
      theme="light"
      duration={duration}
      borderRadius={borderRadius}
      strength={1.0}
      brightness={2.0}
      className={`beam-wrap beam-wrap-${section}`}
    >
      <div className="beam-content">
        <h3>{title}</h3>
        {children}
      </div>
    </BorderBeam>
  );
}
