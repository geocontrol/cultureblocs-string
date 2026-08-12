// Pure sizing math + browser canvas rendering for in-record images.
export function downscaleDims(w, h, maxEdge) {
  const longest = Math.max(w, h);
  if (longest <= maxEdge) return { width: w, height: h };
  const scale = maxEdge / longest;
  return { width: Math.round(w * scale), height: Math.round(h * scale) };
}

// Browser-only. Draws the source into a canvas at `dims`, optional watermark
// text bottom-right, returns a JPEG Blob under the 2MB record budget.
export async function renderToBlob(source, dims, { watermark } = {}) {
  const canvas = document.createElement('canvas');
  canvas.width = dims.width; canvas.height = dims.height;
  const ctx = canvas.getContext('2d');
  ctx.drawImage(source, 0, 0, dims.width, dims.height);
  if (watermark) {
    ctx.font = `${Math.max(12, Math.round(dims.width / 28))}px sans-serif`;
    ctx.textAlign = 'right';
    ctx.fillStyle = 'rgba(255,255,255,0.85)';
    ctx.strokeStyle = 'rgba(0,0,0,0.45)';
    ctx.lineWidth = 2;
    const pad = Math.round(dims.width / 40);
    ctx.strokeText(watermark, dims.width - pad, dims.height - pad);
    ctx.fillText(watermark, dims.width - pad, dims.height - pad);
  }
  let quality = 0.9;
  for (let i = 0; i < 6; i++) {
    const blob = await new Promise(res => canvas.toBlob(res, 'image/jpeg', quality));
    if (blob && blob.size <= 2_000_000) return blob;
    quality -= 0.12;
  }
  return await new Promise(res => canvas.toBlob(res, 'image/jpeg', 0.3));
}
