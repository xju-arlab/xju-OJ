// Statement images are re-encoded as WebP before upload. Quality 0.92 keeps text and
// line art crisp to the eye while cutting screenshots and photos to a fraction.
const WEBP_QUALITY = 0.92
// Wider than any statement column even on 2x screens, so downscaling is invisible.
const MAX_SIDE = 2560
const CONVERTIBLE = /^image\/(png|jpeg|bmp|webp)$/

function encode (canvas) {
  return new Promise(resolve => canvas.toBlob(resolve, 'image/webp', WEBP_QUALITY))
}

export async function compressImageToWebP (file) {
  // GIFs may be animated and anything else is left for the server to judge.
  if (!CONVERTIBLE.test(file.type) || typeof createImageBitmap !== 'function') return file
  let bitmap
  try {
    bitmap = await createImageBitmap(file)
  } catch (_) {
    return file
  }
  const scale = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height))
  const canvas = document.createElement('canvas')
  canvas.width = Math.max(1, Math.round(bitmap.width * scale))
  canvas.height = Math.max(1, Math.round(bitmap.height * scale))
  const context = canvas.getContext('2d')
  context.imageSmoothingQuality = 'high'
  context.drawImage(bitmap, 0, 0, canvas.width, canvas.height)
  if (bitmap.close) bitmap.close()
  const blob = await encode(canvas)
  // Browsers without a WebP encoder fall back to PNG; upload the original then.
  if (!blob || blob.type !== 'image/webp') return file
  if (file.type === 'image/webp' && scale === 1 && blob.size >= file.size) return file
  const name = `${file.name.replace(/\.[^.]*$/, '') || 'image'}.webp`
  return new File([blob], name, { type: 'image/webp' })
}
