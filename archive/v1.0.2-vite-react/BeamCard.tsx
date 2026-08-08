// src/scenario/BeamCard.tsx
// DEPRECATED: v1.0.5 替换为 GlowCard (纯 CSS conic-gradient 旋转光带)
// BorderBeam 1.3 问题: 30% 弧段 + mask 三层 → opacity 0.12-0.26, 肉眼几乎不可见
// 保留此文件仅为避免 import 报错, 实际不再使用
// 新组件: GlowCard.tsx

export { GlowCard as BeamCard } from './GlowCard';
