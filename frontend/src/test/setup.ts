import '@testing-library/jest-dom';

// jsdom 不支持 window.matchMedia，Ant Design 响应式组件依赖此 API
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
});

// jsdom localStorage 兜底：某些环境下未注入 localStorage 全局对象
const __lsStore = new Map<string, string>();
const localStorageMock: Storage = {
  get length() {
    return __lsStore.size;
  },
  clear: () => __lsStore.clear(),
  getItem: (k: string) => __lsStore.get(k) ?? null,
  key: (i: number) => Array.from(__lsStore.keys())[i] ?? null,
  removeItem: (k: string) => {
    __lsStore.delete(k);
  },
  setItem: (k: string, v: string) => {
    __lsStore.set(k, String(v));
  },
};
if (typeof globalThis.localStorage === 'undefined' || !globalThis.localStorage?.setItem) {
  Object.defineProperty(globalThis, 'localStorage', {
    value: localStorageMock,
    configurable: true,
    writable: true,
  });
}
