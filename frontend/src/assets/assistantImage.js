import jpegFallback from './assistente-obras.jpeg'

const transparentAssets = import.meta.glob('./assistente-obras.png', {
  eager: true,
  import: 'default',
  query: '?url',
})

export const assistantImage = transparentAssets['./assistente-obras.png'] || jpegFallback
export const hasTransparentAssistant = Boolean(transparentAssets['./assistente-obras.png'])
