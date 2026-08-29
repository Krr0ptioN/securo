import { useState, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { ChevronDownIcon, ChevronRightIcon, CheckIcon } from 'lucide-react'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Command, CommandInput, CommandList, CommandEmpty, CommandGroup, CommandItem } from '@/components/ui/command'
import type { Category, CategoryGroup } from '@/types'
import { cn, normalizeText } from '@/lib/utils'
import {
  isCategoryHiddenFromSelection,
  resolveSelectedCategory,
} from '@/lib/category-selection-utils'

interface CategorySelectProps {
  value: string
  onChange: (value: string) => void
  categories: Category[]
  groups: CategoryGroup[]
  currentCategory?: Category | null
  placeholder?: string
  disabled?: boolean
  className?: string
  allowNone?: boolean
  contentProps?: React.ComponentProps<typeof PopoverContent>
}

const childrenCount = (parentId: string, categories: Category[]) =>
  categories.filter((category) => category.parent_id === parentId).length


export function CategorySelect({
  value,
  onChange,
  categories,
  currentCategory,
  placeholder,
  disabled = false,
  className,
  allowNone = false,
  contentProps,
}: CategorySelectProps) {
  const [open, setOpen] = useState(false)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [search, setSearch] = useState('')
  const { t } = useTranslation()

  const resolvedPlaceholder = placeholder ?? t('transactions.selectCategory', 'Select category')

  const selectedCategory = useMemo(() => {
    return resolveSelectedCategory(categories ?? [], value, currentCategory)
  }, [categories, currentCategory, value])
  const selectedCategoryIsHidden = isCategoryHiddenFromSelection(
    categories ?? [],
    selectedCategory
  )
  const categoryLabel = (category: Category) =>
    category.path?.length ? category.path.join(' › ') : category.name

  const treeRows = useMemo(() => {
    const visible = (categories ?? []).filter((category) => !category.is_hidden || category.id === value)
    const children = (parentId?: string | null) => visible
      .filter((category) => (category.parent_id ?? null) === (parentId ?? null))
      .sort((a, b) => a.name.localeCompare(b.name))
    const query = normalizeText(search)
    const matches = new Map<string, boolean>()
    const hasMatch = (category: Category): boolean => {
      if (matches.has(category.id)) return matches.get(category.id)!
      const own = normalizeText(categoryLabel(category)).includes(query)
      const descendant = children(category.id).some(hasMatch)
      matches.set(category.id, own || descendant)
      return own || descendant
    }
    const rows: { category: Category; depth: number; hasChildren: boolean }[] = []
    const walk = (category: Category, depth: number) => {
      const nested = children(category.id)
      if (query && !hasMatch(category)) return
      rows.push({ category, depth, hasChildren: nested.length > 0 })
      const showChildren = expanded.has(category.id) || Boolean(query)
      if (showChildren) nested.forEach((child) => walk(child, depth + 1))
    }
    children().forEach((root) => walk(root, 0))
    return rows
  }, [categories, expanded, search, value])

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          disabled={disabled}
          className={cn(
            "flex w-full items-center justify-between gap-2 rounded-md border border-input bg-card px-3 py-2 text-sm text-left shadow-xs transition-[color,box-shadow] outline-hidden focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-input/30 dark:hover:bg-input/50 h-9 cursor-pointer",
            className
          )}
        >
          <span className="flex items-center gap-2 min-w-0 truncate">
            {selectedCategory ? (
              <>
                {selectedCategory.color ? (
                  <span
                    className="size-2.5 shrink-0 rounded-full border border-black/5"
                    style={{ backgroundColor: selectedCategory.color }}
                  />
                ) : null}
                <span className="truncate">{categoryLabel(selectedCategory)}</span>
                {selectedCategoryIsHidden && (
                  <span className="shrink-0 rounded border border-border bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
                    {t('categories.hiddenBadge')}
                  </span>
                )}
              </>
            ) : value === '' && allowNone ? (
              <span className="italic text-muted-foreground truncate">{t('transactions.noCategory')}</span>
            ) : (
              <span className="text-muted-foreground truncate">{resolvedPlaceholder}</span>
            )}
          </span>
          <ChevronDownIcon className="size-4 shrink-0 opacity-50" />
        </button>
      </PopoverTrigger>
      <PopoverContent
        align="start"
        className="w-[var(--radix-popover-trigger-width)] p-0 overflow-hidden"
        {...contentProps}
      >
        <Command filter={() => 1}>
          <CommandInput placeholder={t('transactions.searchCategory')} value={search} onValueChange={setSearch} />
          <CommandList>
            {!treeRows.length && <CommandEmpty>{t('transactions.noCategoryFound')}</CommandEmpty>}
            {allowNone && (
              <CommandGroup>
                <CommandItem
                  value={`none ${t('transactions.noCategory')}`}
                  onSelect={() => {
                    onChange('')
                    setOpen(false)
                  }}
                  className="italic text-muted-foreground cursor-pointer"
                >
                  <span className="flex-1">{t('transactions.noCategory')}</span>
                  {value === '' && <CheckIcon className="size-4 shrink-0" />}
                </CommandItem>
              </CommandGroup>
            )}
            <CommandGroup>
              {treeRows.map(({ category: cat, depth, hasChildren }) => (
                <CommandItem key={cat.id} value={categoryLabel(cat)} onSelect={() => { onChange(cat.id); setOpen(false); setSearch('') }} className="cursor-pointer py-1.5" style={{ paddingLeft: `${8 + depth * 16}px` }}>
                  <button type="button" aria-label={expanded.has(cat.id) ? 'Collapse category' : 'Expand category'} className="mr-1 shrink-0 rounded p-0.5 hover:bg-muted" onClick={(event) => { event.preventDefault(); event.stopPropagation(); setExpanded((previous) => { const next = new Set(previous); if (next.has(cat.id)) next.delete(cat.id); else next.add(cat.id); return next }) }}>
                    {hasChildren ? (expanded.has(cat.id) || search ? <ChevronDownIcon className="size-3.5" /> : <ChevronRightIcon className="size-3.5" />) : <span className="inline-block size-3.5" />}
                  </button>
                  <div className="flex items-center gap-2 min-w-0 truncate flex-1">
                    {cat.color ? <span className="size-2.5 shrink-0 rounded-full border border-black/5" style={{ backgroundColor: cat.color }} /> : null}
                    <span className="truncate">{cat.name}</span>
                  </div>
                  {hasChildren && <span className="text-[10px] text-muted-foreground mr-1">{childrenCount(cat.id, categories)}</span>}
                  {value === cat.id && <CheckIcon className="size-4 shrink-0" />}
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  )
}
