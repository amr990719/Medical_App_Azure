/**
 * Mapping layer between the snake_case API and the camelCase SPA (CLAUDE.md conventions).
 * Only lowercase snake_case keys are converted; data keys such as enum values (`SON_MINOR`)
 * or step numbers stay as the server sent them. The same rule applies at the type level.
 */
type SnakeToCamel<S extends string> = S extends `${infer Head}_${infer Tail}`
  ? `${Head}${Capitalize<SnakeToCamel<Tail>>}`
  : S;

type CamelKey<K> = K extends string ? (K extends Lowercase<K> ? SnakeToCamel<K> : K) : K;

export type Camelize<T> = T extends readonly (infer U)[]
  ? Camelize<U>[]
  : T extends Record<string, unknown>
    ? { [K in keyof T as CamelKey<K>]: Camelize<T[K]> }
    : T;

type CamelToSnake<S extends string> = S extends `${infer Head}${infer Tail}`
  ? `${Head extends Lowercase<Head> ? Head : `_${Lowercase<Head>}`}${CamelToSnake<Tail>}`
  : S;

export type Snakeize<T> = T extends readonly (infer U)[]
  ? Snakeize<U>[]
  : T extends Record<string, unknown>
    ? { [K in keyof T as K extends string ? CamelToSnake<K> : K]: Snakeize<T[K]> }
    : T;

const isPlainObject = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && Object.getPrototypeOf(value) === Object.prototype;

function mapKeys(value: unknown, convert: (key: string) => string): unknown {
  if (Array.isArray(value)) return value.map((item) => mapKeys(item, convert));
  if (!isPlainObject(value)) return value;
  return Object.fromEntries(
    Object.entries(value).map(([key, inner]) => [convert(key), mapKeys(inner, convert)]),
  );
}

const camelKey = (key: string) =>
  key === key.toLowerCase() ? key.replace(/_([a-z0-9])/g, (_, c: string) => c.toUpperCase()) : key;

const snakeKey = (key: string) => key.replace(/[A-Z]/g, (c) => `_${c.toLowerCase()}`);

export function toCamel<T>(value: T): Camelize<T> {
  return mapKeys(value, camelKey) as Camelize<T>;
}

export function toSnake<T>(value: T): Snakeize<T> {
  return mapKeys(value, snakeKey) as Snakeize<T>;
}
