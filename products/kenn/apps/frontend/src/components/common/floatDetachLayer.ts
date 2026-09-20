/**
 * Mix Review 浮窗 + KENN 侧边栏共享的层叠 / 错开状态。
 * 必须放在独立模块：script setup 内的 let 是「每实例一份」，无法跨层置顶。
 */
let floatZ = 200
let floatCascade = 0

export function nextFloatZ() {
  floatZ += 1
  return floatZ
}

export function nextFloatCascadeStep() {
  floatCascade += 1
  return ((floatCascade - 1) % 8) * 32
}

/** 浮窗 Teleport 目标：与 KENN 侧栏同层，才能互相点选置顶 */
export const FLOAT_TELEPORT_HOST = '#mix-float-root'
