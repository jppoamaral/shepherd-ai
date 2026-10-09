import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { Icon, IconName } from './icon';

const BADGES: Record<string, { cls: string; icon: IconName; label: string }> = {
  new: { cls: 'sh-badge--new', icon: 'sprout', label: 'New' },
  experienced: { cls: 'sh-badge--exp', icon: 'checkCircle', label: 'Experienced' },
  veteran: { cls: 'sh-badge--vet', icon: 'star', label: 'Veteran' },
};

/** Experience in a role, always icon + word (status is never color alone). */
@Component({
  selector: 'sh-experience',
  imports: [Icon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { style: 'display:contents' },
  template: `@if (badge(); as b) {<span class="sh-badge" [class]="'sh-badge ' + b.cls"><sh-icon [name]="b.icon" />{{ b.label }}</span>}`,
})
export class ExperienceBadge {
  readonly level = input<string | null | undefined>(null);
  protected readonly badge = computed(() => BADGES[this.level() ?? ''] ?? null);
}
