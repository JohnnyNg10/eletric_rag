/**
 * 生成UUID v4
 * 兼容不支持 crypto.randomUUID() 的环境
 */
export function generateUUID(): string {
  // 优先使用原生API（HTTPS环境）
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID();
  }

  // Fallback: 使用Math.random()实现RFC4122 v4 UUID
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}
