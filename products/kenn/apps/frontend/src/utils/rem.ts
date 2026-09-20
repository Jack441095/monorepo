/** 设计稿宽度（PC 网页常用 1920） */
const DESIGN_WIDTH = 1920
/**
 * rem 基准：设计稿下 1rem = 100px
 * 写法：设计稿 px ÷ 100 = rem，例如 16px → 0.16rem
 */
const BASE_FONT_SIZE = 100
/** 对应最小屏宽约 1280px */
const MIN_FONT_SIZE = 66.67
/** 对应设计稿宽度 1920px，更大屏不再放大 */
const MAX_FONT_SIZE = 100

const setRem = () => {
  const width = document.documentElement.clientWidth
  const fontSize = (width / DESIGN_WIDTH) * BASE_FONT_SIZE
  const clamped = Math.min(Math.max(fontSize, MIN_FONT_SIZE), MAX_FONT_SIZE)
  document.documentElement.style.fontSize = `${clamped}px`
}

setRem()
window.addEventListener('resize', setRem)
