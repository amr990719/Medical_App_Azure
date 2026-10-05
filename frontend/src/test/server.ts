import { setupServer } from "msw/node";

/** One MSW server for every test; each test registers its own handlers with server.use(). */
export const server = setupServer();
