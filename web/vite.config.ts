import {defineConfig} from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig({plugins:[react()],server:{proxy:{'/local':'http://127.0.0.1:18765','/remote':'http://127.0.0.1:18765'}}});
