// Sustituye a src/mock/index.ts en cualquier build sin VITE_MOCK=1 (ver vite.config.ts),
// para que ni el código ni los videos simulados acaben en el bundle real.
export function installMock(): void {
  throw new Error('El modo mock no está incluido en este build.');
}
