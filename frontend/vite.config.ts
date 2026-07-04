import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
  build: {
    // Экспорт (jspdf/xlsx) вынесен в ленивый чанк и грузится только по клику,
    // поэтому его размер не влияет на первичную загрузку — поднимаем порог.
    chunkSizeWarningLimit: 800,
  },
})
