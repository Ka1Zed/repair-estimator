import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'node',
  },
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
    },
  },
  build: {
    // Экспорт (jspdf/xlsx) вынесен в ленивый чанк (~1.3 МБ) и грузится только
    // по клику, поэтому его размер не влияет на первичную загрузку — поднимаем
    // порог выше фактического размера чанка, чтобы сборка была без предупреждений.
    chunkSizeWarningLimit: 1500,
  },
})
