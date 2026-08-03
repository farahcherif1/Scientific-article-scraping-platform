import { useEffect, useId, useRef, useState } from "react";
import { Check, ChevronDown } from "lucide-react";

export interface SelectOption<T extends string> {
  value: T;
  label: string;
}

interface Props<T extends string> {
  value: T;
  onChange: (value: T) => void;
  options: SelectOption<T>[];
  id?: string;
  disabled?: boolean;
  className?: string;
  "aria-label"?: string;
}

/**
 * Accessible custom dropdown replacing the native <select> across the app -
 * native selects can't be styled to match the emerald/slate design system
 * (the popup renders with raw OS chrome), so this owns its own popup,
 * keyboard nav (arrows/home/end/enter/escape/typeahead), and ARIA wiring
 * (combobox/listbox/option) instead.
 */
export default function Select<T extends string>({
  value,
  onChange,
  options,
  id,
  disabled,
  className,
  "aria-label": ariaLabel,
}: Props<T>) {
  const [isOpen, setIsOpen] = useState(false);
  const [highlighted, setHighlighted] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const typeaheadRef = useRef("");
  const typeaheadTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const generatedId = useId();
  const buttonId = id ?? generatedId;
  const listboxId = `${buttonId}-listbox`;

  const selectedIndex = Math.max(
    0,
    options.findIndex((o) => o.value === value)
  );
  const selected = options[selectedIndex];

  useEffect(() => {
    if (!isOpen) return;
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    const el = listRef.current?.children[highlighted] as HTMLElement | undefined;
    // Optional call: jsdom (unit tests) doesn't implement scrollIntoView.
    el?.scrollIntoView?.({ block: "nearest" });
  }, [isOpen, highlighted]);

  // Opens the popup with the currently-selected option highlighted. Called
  // directly from event handlers (click/keydown), never from an effect, so
  // the setState pair here is a normal synchronous UI update rather than
  // something react-hooks/set-state-in-effect would flag.
  function openList() {
    setHighlighted(selectedIndex);
    setIsOpen(true);
  }

  function toggleOpen() {
    if (isOpen) setIsOpen(false);
    else openList();
  }

  function commit(index: number) {
    const option = options[index];
    if (!option) return;
    onChange(option.value);
    setIsOpen(false);
  }

  function handleTypeahead(char: string) {
    if (typeaheadTimerRef.current) clearTimeout(typeaheadTimerRef.current);
    typeaheadRef.current += char.toLowerCase();
    typeaheadTimerRef.current = setTimeout(() => {
      typeaheadRef.current = "";
    }, 500);
    const match = options.findIndex((o) =>
      o.label.toLowerCase().startsWith(typeaheadRef.current)
    );
    if (match >= 0) setHighlighted(match);
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (disabled) return;
    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        if (!isOpen) openList();
        else setHighlighted((h) => Math.min(options.length - 1, h + 1));
        break;
      case "ArrowUp":
        e.preventDefault();
        if (!isOpen) openList();
        else setHighlighted((h) => Math.max(0, h - 1));
        break;
      case "Home":
        if (isOpen) {
          e.preventDefault();
          setHighlighted(0);
        }
        break;
      case "End":
        if (isOpen) {
          e.preventDefault();
          setHighlighted(options.length - 1);
        }
        break;
      case "Enter":
      case " ":
        e.preventDefault();
        if (isOpen) commit(highlighted);
        else openList();
        break;
      case "Escape":
        if (isOpen) {
          e.preventDefault();
          setIsOpen(false);
        }
        break;
      case "Tab":
        setIsOpen(false);
        break;
      default:
        if (e.key.length === 1 && /\S/.test(e.key)) {
          if (!isOpen) openList();
          handleTypeahead(e.key);
        }
    }
  }

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        id={buttonId}
        disabled={disabled}
        onClick={toggleOpen}
        onKeyDown={handleKeyDown}
        role="combobox"
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        aria-controls={listboxId}
        aria-label={ariaLabel}
        className={
          className ??
          "flex w-full items-center justify-between gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-left text-sm text-slate-700 hover:border-slate-300 focus:outline-none focus:ring-2 focus:ring-emerald-500 disabled:cursor-not-allowed disabled:bg-slate-50 disabled:text-slate-400"
        }
      >
        <span className="truncate">{selected?.label ?? ""}</span>
        <ChevronDown
          className={`h-4 w-4 shrink-0 text-slate-400 transition-transform ${isOpen ? "rotate-180" : ""}`}
          aria-hidden="true"
        />
      </button>

      {isOpen && (
        <ul
          ref={listRef}
          id={listboxId}
          role="listbox"
          aria-activedescendant={`${listboxId}-option-${highlighted}`}
          tabIndex={-1}
          className="absolute z-20 mt-1 max-h-60 w-full min-w-max overflow-auto rounded-lg border border-slate-200 bg-white py-1 text-sm shadow-lg"
        >
          {options.map((option, index) => {
            const isSelected = option.value === value;
            const isHighlighted = index === highlighted;
            return (
              <li
                key={option.value}
                id={`${listboxId}-option-${index}`}
                role="option"
                aria-selected={isSelected}
                onMouseEnter={() => setHighlighted(index)}
                onClick={() => commit(index)}
                className={`flex cursor-pointer items-center justify-between gap-2 px-3 py-2 ${
                  isHighlighted ? "bg-emerald-50 text-emerald-700" : "text-slate-700"
                }`}
              >
                <span className="truncate">{option.label}</span>
                {isSelected && <Check className="h-3.5 w-3.5 shrink-0 text-emerald-600" aria-hidden="true" />}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
