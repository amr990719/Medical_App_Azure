/** Full-page navigations, wrapped so tests can observe them (jsdom cannot navigate). */
export const browser = {
  assign(url: string): void {
    window.location.assign(url);
  },
};
