import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/Button";
import { ar } from "@/i18n/ar";
import { normalizeDigits } from "@/utils/digits";

/**
 * Search runs on submit (Enter or the button), not on every keystroke: each query is a server
 * request over a large table. Arabic digits are normalized before they leave the browser.
 */
export function SearchBox({
  initial,
  placeholder,
  onSearch,
}: {
  initial: string;
  placeholder: string;
  onSearch: (value: string) => void;
}) {
  const [value, setValue] = useState(initial);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    onSearch(normalizeDigits(value).trim());
  };

  return (
    <form role="search" onSubmit={submit} className="flex min-w-0 flex-1 gap-2">
      <label className="sr-only" htmlFor="admin-search">
        {ar.admin.list.search}
      </label>
      <input
        id="admin-search"
        type="search"
        value={value}
        onChange={(event) => setValue(event.target.value)}
        placeholder={placeholder}
        className="min-h-10 min-w-0 flex-1 rounded-lg border border-border-hover bg-white px-3 text-sm placeholder:text-muted focus:border-teal"
      />
      <Button type="submit" variant="outline">
        {ar.admin.list.searchButton}
      </Button>
    </form>
  );
}
