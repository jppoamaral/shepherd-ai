import { Injectable } from '@angular/core';
import { Observable, of } from 'rxjs';
import type {
  AskAnswer,
  AskDraft,
  AskIn,
  AskSendOut,
  AskStart,
  Briefing,
  ChatMessage,
  ChatThread,
  Church,
  Huddle,
  Leader,
  Memory,
  MemoryPending,
  Ministry,
  Notice,
  Proposal,
  Roster,
  SuggestedAssignment,
  Suggestion,
  Volunteer,
} from './types';

const CHURCH_ID = 'demo-grace';
const KIDS_ID = 'demo-kids';
const WORSHIP_ID = 'demo-worship';
const MARIA_ID = 'demo-maria';
const ANNA_ID = 'demo-anna';
const RACHEL_ID = 'demo-rachel';
const EMILY_ID = 'demo-emily';
const GATHERING_ID = 'demo-sunday';
const ROLE_HELPER_ID = 'demo-helper';
const ROLE_LEADER_ID = 'demo-leader';
const NOW = '2026-10-16T22:00:00.000Z';

function typed<T>(value: unknown): T {
  return value as T;
}

@Injectable({ providedIn: 'root' })
export class DemoApiService {
  private proposals: Proposal[] = [
    typed<Proposal>({
      id: 'demo-proposal-memory',
      type: 'memory',
      status: 'pending',
      created_by_agent: 'steward',
      created_at: NOW,
      decided_by_person_id: null,
      decided_at: null,
      payload: { ministry_id: KIDS_ID },
      title: 'A pattern Shepherd noticed',
      summary: 'Keep new helpers beside a veteran for their first month.',
      count: null,
    }),
    typed<Proposal>({
      id: 'demo-proposal-roster',
      type: 'leader_roster',
      status: 'pending',
      created_by_agent: 'roster',
      created_at: NOW,
      decided_by_person_id: null,
      decided_at: null,
      payload: { ministry_id: KIDS_ID },
      title: 'Kids roster suggestion',
      summary: 'A training roster is ready for your review.',
      count: 2,
    }),
  ];

  private memories: Record<string, unknown[]> = {
    [KIDS_ID]: [
      {
        id: 'demo-memory-1',
        kind: 'habit',
        text: 'Keep new helpers beside a veteran for their first month.',
        about: null,
        proposed_from: 'leader_note',
        confirmed_by: 'Maria Lopez',
        created_at: NOW,
      },
    ],
    [WORSHIP_ID]: [],
  };

  private readonly churchesData: Church[] = [
    typed<Church>({
      id: CHURCH_ID,
      name: 'Grace Community',
      timezone: 'America/Chicago',
      language: 'en',
      profile_status: 'approved',
      member_count: 24,
      load_rules: [{ period: 'week', normal_max: 2, warning_above: 3 }],
    }),
  ];

  private readonly leadersData: Leader[] = [
    typed<Leader>({
      person_id: MARIA_ID,
      name: 'Maria Lopez',
      ministries: [
        { ministry_id: KIDS_ID, ministry: 'Kids', can_schedule: true, can_approve: true },
        { ministry_id: WORSHIP_ID, ministry: 'Worship', can_schedule: false, can_approve: true },
      ],
    }),
    typed<Leader>({
      person_id: ANNA_ID,
      name: 'Anna Parker',
      ministries: [{ ministry_id: KIDS_ID, ministry: 'Kids', can_schedule: true, can_approve: false }],
    }),
    typed<Leader>({
      person_id: RACHEL_ID,
      name: 'Rachel Green',
      ministries: [{ ministry_id: WORSHIP_ID, ministry: 'Worship', can_schedule: true, can_approve: true }],
    }),
  ];

  private readonly volunteersData: Volunteer[] = [
    typed<Volunteer>({ person_id: ANNA_ID, name: 'Anna Parker', ministry: 'Kids' }),
    typed<Volunteer>({ person_id: EMILY_ID, name: 'Emily Stone', ministry: 'Kids' }),
    typed<Volunteer>({ person_id: RACHEL_ID, name: 'Rachel Green', ministry: 'Worship' }),
  ];

  churches(): Observable<Church[]> {
    return of(this.churchesData);
  }

  leaders(churchId: string): Observable<Leader[]> {
    return of(churchId === CHURCH_ID ? this.leadersData : []);
  }

  ministries(churchId: string): Observable<Ministry[]> {
    if (churchId !== CHURCH_ID) return of([]);
    return of([
      typed<Ministry>({
        id: KIDS_ID,
        name: 'Kids',
        aliases: ['Kids ministry'],
        show_both_paths: true,
        default_path: 'training',
        draft_horizon_weeks: 1,
        roles: [
          { id: ROLE_HELPER_ID, name: 'Helper', minimums: [{ gathering_type_id: GATHERING_ID, minimum: 2 }] },
          { id: ROLE_LEADER_ID, name: 'Team lead', minimums: [{ gathering_type_id: GATHERING_ID, minimum: 1 }] },
        ],
        leaders: [{ person_id: MARIA_ID, name: 'Maria Lopez', can_schedule: true, can_approve: true }],
      }),
      typed<Ministry>({
        id: WORSHIP_ID,
        name: 'Worship',
        aliases: ['Band'],
        show_both_paths: true,
        default_path: 'veteran',
        draft_horizon_weeks: 1,
        roles: [{ id: ROLE_LEADER_ID, name: 'Leader', minimums: [{ gathering_type_id: GATHERING_ID, minimum: 1 }] }],
        leaders: [{ person_id: RACHEL_ID, name: 'Rachel Green', can_schedule: true, can_approve: true }],
      }),
    ]);
  }

  briefing(churchId: string, personId: string): Observable<Briefing> {
    return of(
      typed<Briefing>({
        person_id: personId,
        name: this.leadersData.find((l) => l.person_id === personId)?.name ?? 'Maria Lopez',
        start: '2026-10-18',
        end: '2026-10-24',
        headline: 'A calm week with two things worth your attention.',
        items: [
          {
            finding_id: 'finding-overlap',
            type: 'overlap',
            severity: 'warning',
            text: 'Anna Parker is scheduled in Kids and Worship at the same time.',
            on: '2026-10-18',
            ministries: ['Kids', 'Worship'],
            people: ['Anna Parker'],
            can_huddle: true,
            fill: null,
          },
          {
            finding_id: 'finding-gap',
            type: 'below_minimum',
            severity: 'warning',
            text: 'Kids is missing one Helper for Sunday.',
            on: '2026-10-18',
            ministries: ['Kids'],
            people: [],
            can_huddle: false,
            fill: {
              ministry_id: KIDS_ID,
              gathering_id: GATHERING_ID,
              role_id: ROLE_HELPER_ID,
              role: 'Helper',
              person_id: EMILY_ID,
              name: 'Emily Stone',
            },
          },
        ],
        gatherings: [
          {
            gathering_id: GATHERING_ID,
            ministry_id: KIDS_ID,
            ministry: 'Kids',
            name: 'Sunday service',
            start_at: '2026-10-18T09:30:00-05:00',
            needed: 3,
            filled: 2,
          },
        ],
      }),
    );
  }

  roster(churchId: string, ministryId: string, start?: string, end?: string): Observable<Roster> {
    return of(this.rosterData(ministryId, start ?? '2026-10-18', end ?? '2026-10-25'));
  }

  suggestion(churchId: string, ministryId: string): Observable<Suggestion> {
    const lines = ministryId === WORSHIP_ID
      ? [{ gathering_id: GATHERING_ID, gathering: 'Sunday service', start_at: '2026-10-18T09:30:00-05:00', role_id: ROLE_LEADER_ID, role: 'Leader', person_id: RACHEL_ID, name: 'Rachel Green', experience: 'veteran', reason: 'Rachel is a veteran in this role.', flags: [], alternatives: [] }]
      : [
          { gathering_id: GATHERING_ID, gathering: 'Sunday service', start_at: '2026-10-18T09:30:00-05:00', role_id: ROLE_HELPER_ID, role: 'Helper', person_id: EMILY_ID, name: 'Emily Stone', experience: 'experienced', reason: 'Emily pairs well with Anna while she grows in this role.', flags: [], alternatives: [{ person_id: ANNA_ID, name: 'Anna Parker', experience: 'veteran' }] },
          { gathering_id: GATHERING_ID, gathering: 'Sunday service', start_at: '2026-10-18T09:30:00-05:00', role_id: ROLE_LEADER_ID, role: 'Team lead', person_id: MARIA_ID, name: 'Maria Lopez', experience: 'veteran', reason: 'Maria is a veteran team lead.', flags: [], alternatives: [] },
        ];
    return of(typed<Suggestion>({ ministry_id: ministryId, ministry: ministryId === WORSHIP_ID ? 'Worship' : 'Kids', start: '2026-10-18', end: '2026-10-25', lines, open: 0 }));
  }

  pendingProposals(churchId: string): Observable<Proposal[]> {
    return of(this.proposals.filter((p) => p.status === 'pending'));
  }

  approve(churchId: string, proposalId: string, personId: string): Observable<Proposal> {
    const proposal = this.proposals.find((p) => p.id === proposalId);
    if (proposal) {
      proposal.status = 'approved';
      proposal.decided_by_person_id = personId;
      if (proposal.type === 'memory') {
        const ministryId = String(proposal.payload['ministry_id'] ?? KIDS_ID);
        this.memories[ministryId] ??= [];
        this.memories[ministryId].push({
          id: `memory-${Date.now()}`,
          kind: 'rule',
          text: proposal.summary,
          about: null,
          proposed_from: 'leader_note',
          confirmed_by: 'Maria Lopez',
          created_at: NOW,
        });
      }
    }
    return of(proposal ?? typed<Proposal>({ id: proposalId }));
  }

  reject(churchId: string, proposalId: string, personId: string): Observable<Proposal> {
    const proposal = this.proposals.find((p) => p.id === proposalId);
    if (proposal) {
      proposal.status = 'rejected';
      proposal.decided_by_person_id = personId;
    }
    return of(proposal ?? typed<Proposal>({ id: proposalId }));
  }

  approveSuggestion(churchId: string, ministryId: string, personId: string, assignments: SuggestedAssignment[]): Observable<Proposal> {
    return of(typed<Proposal>({ id: `approved-${Date.now()}`, type: 'leader_roster', status: 'approved', created_by_agent: 'leader', created_at: NOW, decided_by_person_id: personId, decided_at: NOW, payload: { ministry_id: ministryId, assignments }, title: 'Roster approved', summary: 'The selected roster was recorded.', count: assignments.length }));
  }

  startHuddle(churchId: string, findingId: string, personId: string): Observable<Huddle> {
    return of(this.huddleData(findingId, 'open'));
  }

  chooseSlot(churchId: string, huddleId: string, personId: string, slotId: string): Observable<Huddle> {
    const h = this.huddleData('finding-overlap', 'scheduled');
    h.chosen_slot = h.slots.find((s) => s.id === slotId) ?? h.slots[0];
    return of(h);
  }

  acceptReplacement(churchId: string, huddleId: string, personId: string, ministryId: string): Observable<Huddle> {
    const h = this.huddleData('finding-overlap', 'scheduled');
    h.replacement = { ministry_id: ministryId, ministry: ministryId === KIDS_ID ? 'Kids' : 'Worship', resolved_by: 'Maria Lopez', volunteer: 'Anna Parker', replacement: 'Emily Stone', can_undo: true };
    return of(h);
  }

  undoReplacement(churchId: string, huddleId: string, personId: string): Observable<Huddle> {
    return of(this.huddleData('finding-overlap', 'scheduled'));
  }

  resolveHuddle(churchId: string, huddleId: string, personId: string, outcome: string): Observable<Huddle> {
    const h = this.huddleData('finding-overlap', 'resolved');
    h.outcome = outcome;
    return of(h);
  }

  volunteers(churchId: string): Observable<Volunteer[]> {
    return of(this.volunteersData);
  }

  chat(churchId: string, personId: string): Observable<ChatThread> {
    return of(typed<ChatThread>({
      person_id: personId,
      name: this.volunteersData.find((v) => v.person_id === personId)?.name ?? 'Anna Parker',
      church: 'Grace Community',
      channel: 'simulator',
      messages: [
        { id: 'chat-1', body: 'Hi Anna — are you able to serve this Sunday at 9:30?', buttons: ['Yes, I can serve', 'I can’t make it'], at: '2026-10-16T18:00:00.000Z', approved: true },
      ],
    }));
  }

  say(churchId: string, personId: string, text: string): Observable<{ replies: ChatMessage[] }> {
    return of({ replies: [typed<ChatMessage>({ id: `chat-${Date.now()}`, body: text.toLowerCase().includes('yes') ? 'Thanks — I’ll tell your leader.' : 'Thanks for letting Shepherd know. I’ll tell your leader.', buttons: [], at: NOW, approved: true })] });
  }

  notices(churchId: string, personId: string): Observable<Notice[]> {
    return of([
      typed<Notice>({ id: 'notice-1', ministry_id: KIDS_ID, about: 'Anna Parker', kind: 'can_serve', text: 'Anna said she can serve this Sunday.', note: null, at: NOW, settled: false }),
    ]);
  }

  dismissNotice(churchId: string, noticeId: string, personId: string): Observable<void> {
    return of(void 0);
  }

  putIn(churchId: string, noticeId: string, personId: string): Observable<{ text: string }> {
    return of({ text: 'Anna Parker is on the roster as Helper.' });
  }

  draftReminders(churchId: string, ministryId: string): Observable<unknown> {
    return of({});
  }

  askStart(churchId: string, ministryId: string, personId: string): Observable<AskStart> {
    return of(typed<AskStart>({ ministry: ministryId === WORSHIP_ID ? 'Worship' : 'Kids', greeting: 'What would you like to look up?', suggestions: [{ kind: 'ask', label: 'Who is serving this Sunday?', intent: 'roster' }] }));
  }

  ask(churchId: string, ministryId: string, body: AskIn): Observable<AskAnswer> {
    const draft: AskDraft = typed<AskDraft>({ to_person_id: ANNA_ID, to: 'Anna Parker', body: 'Hi Anna — are you able to serve this Sunday at 9:30?', kind: 'ask', gathering_id: GATHERING_ID, role_id: ROLE_HELPER_ID, assignment_id: null, replaces_assignment_id: null, replaces: null });
    return of(typed<AskAnswer>({ intent: 'roster', text: 'Anna Parker and Emily Stone are serving in Kids this Sunday at 9:30.', people: [{ person_id: ANNA_ID, name: 'Anna Parker', experience: 'veteran' }, { person_id: EMILY_ID, name: 'Emily Stone', experience: 'experienced' }], notes: [], drafts: [draft], actions: [], source: 'demo record', looked_at: ['Kids roster', 'Sunday service'], refused: false }));
  }

  sendDrafts(churchId: string, ministryId: string, personId: string, drafts: AskDraft[]): Observable<AskSendOut> {
    return of(typed<AskSendOut>({ sent: drafts.map((d) => d.to_person_id), skipped: [], text: `Sent ${drafts.length} message${drafts.length === 1 ? '' : 's'} 1:1.` }));
  }

  memory(churchId: string, ministryId: string): Observable<Memory> {
    return of(typed<Memory>({ ministry_id: ministryId, ministry: ministryId === WORSHIP_ID ? 'Worship' : 'Kids', items: this.memories[ministryId] ?? [], pending: this.proposals.filter((p) => p.status === 'pending' && p.type === 'memory').map((p) => typed<MemoryPending>({ proposal_id: p.id, kind: 'rule', text: p.summary, about: null, question: 'Remember this?' })) }));
  }

  noteMemory(churchId: string, ministryId: string, personId: string, text: string): Observable<MemoryPending> {
    const id = `demo-note-${Date.now()}`;
    this.proposals.push(typed<Proposal>({ id, type: 'memory', status: 'pending', created_by_agent: 'leader_note', created_at: NOW, decided_by_person_id: null, decided_at: null, payload: { ministry_id: ministryId }, title: 'Memory suggestion', summary: text, count: null }));
    return of(typed<MemoryPending>({ proposal_id: id, kind: 'rule', text, about: null, question: 'Remember this?' }));
  }

  deleteMemory(churchId: string, ministryId: string, memoryId: string, personId: string): Observable<void> {
    this.memories[ministryId] = (this.memories[ministryId] ?? []).filter((item) => (item as { id: string }).id !== memoryId);
    return of(void 0);
  }

  private rosterData(ministryId: string, start: string, end: string): Roster {
    return typed<Roster>({
      ministry_id: ministryId,
      ministry: ministryId === WORSHIP_ID ? 'Worship' : 'Kids',
      start,
      end,
      gatherings: [{
        gathering_id: GATHERING_ID,
        name: 'Sunday service',
        kind: 'regular',
        start_at: '2026-10-18T09:30:00-05:00',
        end_at: '2026-10-18T11:00:00-05:00',
        roles: [{
          role_id: ministryId === WORSHIP_ID ? ROLE_LEADER_ID : ROLE_HELPER_ID,
          role: ministryId === WORSHIP_ID ? 'Leader' : 'Helper',
          minimum: 2,
          missing: 0,
          people: [{ assignment_id: 'assignment-1', person_id: ministryId === WORSHIP_ID ? RACHEL_ID : EMILY_ID, name: ministryId === WORSHIP_ID ? 'Rachel Green' : 'Emily Stone', status: 'approved', experience: 'experienced', flags: [] }],
        }],
      }],
    });
  }

  private huddleData(findingId: string, status: 'open' | 'scheduled' | 'resolved'): Huddle {
    return typed<Huddle>({
      id: 'huddle-demo',
      finding_id: findingId,
      status,
      leaders: [{ person_id: MARIA_ID, name: 'Maria Lopez' }, { person_id: RACHEL_ID, name: 'Rachel Green' }],
      slots: [
        { id: 'slot-1', start_at: '2026-10-17T18:00:00-05:00', end_at: '2026-10-17T18:15:00-05:00', label: 'Saturday at 6:00 PM' },
        { id: 'slot-2', start_at: '2026-10-17T18:30:00-05:00', end_at: '2026-10-17T18:45:00-05:00', label: 'Saturday at 6:30 PM' },
      ],
      chosen_slot: status === 'scheduled' ? { id: 'slot-1', start_at: '2026-10-17T18:00:00-05:00', end_at: '2026-10-17T18:15:00-05:00', label: 'Saturday at 6:00 PM' } : null,
      no_common_slot: false,
      nearest_options: [],
      agenda: { title: 'Anna Parker, Sunday service', volunteer: 'Anna Parker', sides: [{ ministry: 'Kids', ministry_id: KIDS_ID, role: 'Helper', gathering: 'Sunday service', leader: 'Maria Lopez', replacement: 'Emily Stone', replacement_person_id: EMILY_ID }, { ministry: 'Worship', ministry_id: WORSHIP_ID, role: 'Leader', gathering: 'Sunday service', leader: 'Rachel Green', replacement: 'Rachel Green', replacement_person_id: RACHEL_ID }] },
      agenda_text: 'Talk through Anna Parker’s overlapping Sunday assignments and choose one roster path.',
      outcome: status === 'resolved' ? 'Maria Lopez will use the Kids replacement.' : null,
      finding_status: status === 'resolved' ? 'resolved' : 'open',
      replacement: null,
    });
  }
}
