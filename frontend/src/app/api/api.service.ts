import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';
import { DemoApiService } from './demo-api.service';
import type {
  AskAnswer,
  AskDraft,
  AskSendOut,
  PutInOut,
  ChatMessage,
  ChatThread,
  Notice,
  Volunteer,
  AskIn,
  AskStart,
  Briefing,
  Church,
  Huddle,
  Leader,
  Memory,
  MemoryPending,
  Ministry,
  Proposal,
  Roster,
  SuggestedAssignment,
  Suggestion,
} from './types';

/** One typed method per endpoint the app uses (see docs/demo.md, "API map"). */
@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);
  private readonly demo = inject(DemoApiService);
  private readonly base = environment.apiUrl;

  churches(): Observable<Church[]> {
    if (environment.demo) return this.demo.churches();
    return this.http.get<Church[]>(`${this.base}/churches`);
  }

  leaders(churchId: string): Observable<Leader[]> {
    if (environment.demo) return this.demo.leaders(churchId);
    return this.http.get<Leader[]>(`${this.base}/churches/${churchId}/leaders`);
  }

  ministries(churchId: string): Observable<Ministry[]> {
    if (environment.demo) return this.demo.ministries(churchId);
    return this.http.get<Ministry[]>(`${this.base}/churches/${churchId}/ministries`);
  }

  briefing(churchId: string, personId: string): Observable<Briefing> {
    if (environment.demo) return this.demo.briefing(churchId, personId);
    return this.http.get<Briefing>(`${this.base}/churches/${churchId}/leaders/${personId}/briefing`);
  }

  roster(churchId: string, ministryId: string, start?: string, end?: string): Observable<Roster> {
    if (environment.demo) return this.demo.roster(churchId, ministryId, start, end);
    const params: Record<string, string> = {};
    if (start) params['start'] = start;
    if (end) params['end'] = end;
    return this.http.get<Roster>(`${this.base}/churches/${churchId}/ministries/${ministryId}/roster`, { params });
  }

  suggestion(churchId: string, ministryId: string): Observable<Suggestion> {
    if (environment.demo) return this.demo.suggestion(churchId, ministryId);
    return this.http.get<Suggestion>(`${this.base}/churches/${churchId}/ministries/${ministryId}/suggestion`);
  }

  approveSuggestion(
    churchId: string,
    ministryId: string,
    personId: string,
    assignments: SuggestedAssignment[],
  ): Observable<Proposal> {
    if (environment.demo) return this.demo.approveSuggestion(churchId, ministryId, personId, assignments);
    return this.http.post<Proposal>(`${this.base}/churches/${churchId}/ministries/${ministryId}/suggestion/approve`, {
      person_id: personId,
      assignments,
    });
  }

  pendingProposals(churchId: string): Observable<Proposal[]> {
    if (environment.demo) return this.demo.pendingProposals(churchId);
    return this.http.get<Proposal[]>(`${this.base}/churches/${churchId}/proposals`, {
      params: { status: 'pending' },
    });
  }

  approve(churchId: string, proposalId: string, personId: string): Observable<Proposal> {
    if (environment.demo) return this.demo.approve(churchId, proposalId, personId);
    return this.http.post<Proposal>(`${this.base}/churches/${churchId}/proposals/${proposalId}/approve`, {
      person_id: personId,
    });
  }

  reject(churchId: string, proposalId: string, personId: string): Observable<Proposal> {
    if (environment.demo) return this.demo.reject(churchId, proposalId, personId);
    return this.http.post<Proposal>(`${this.base}/churches/${churchId}/proposals/${proposalId}/reject`, {
      person_id: personId,
    });
  }

  startHuddle(churchId: string, findingId: string, personId: string): Observable<Huddle> {
    if (environment.demo) return this.demo.startHuddle(churchId, findingId, personId);
    return this.http.post<Huddle>(`${this.base}/churches/${churchId}/findings/${findingId}/huddle`, {
      person_id: personId,
    });
  }

  chooseSlot(churchId: string, huddleId: string, personId: string, slotId: string): Observable<Huddle> {
    if (environment.demo) return this.demo.chooseSlot(churchId, huddleId, personId, slotId);
    return this.http.post<Huddle>(`${this.base}/churches/${churchId}/huddles/${huddleId}/choose`, {
      person_id: personId,
      slot_id: slotId,
    });
  }

  /** Volunteer chat (demo): people on a team, for the "open a volunteer's chat" picker. */
  volunteers(churchId: string): Observable<Volunteer[]> {
    if (environment.demo) return this.demo.volunteers(churchId);
    return this.http.get<Volunteer[]>(`${this.base}/churches/${churchId}/volunteers`);
  }

  /** Shepherd's side of one person's chat. */
  chat(churchId: string, personId: string): Observable<ChatThread> {
    if (environment.demo) return this.demo.chat(churchId, personId);
    return this.http.get<ChatThread>(`${this.base}/churches/${churchId}/people/${personId}/chat`);
  }

  /** The volunteer writes (or taps a button): the same handling Telegram will use. */
  say(churchId: string, personId: string, text: string): Observable<{ replies: ChatMessage[] }> {
    if (environment.demo) return this.demo.say(churchId, personId, text);
    return this.http.post<{ replies: ChatMessage[] }>(`${this.base}/churches/${churchId}/people/${personId}/chat`, {
      text,
    });
  }

  /** What volunteers asked Shepherd to pass on to this leader. */
  notices(churchId: string, personId: string): Observable<Notice[]> {
    if (environment.demo) return this.demo.notices(churchId, personId);
    return this.http.get<Notice[]>(`${this.base}/churches/${churchId}/leaders/${personId}/notices`);
  }

  /** Dismissing deletes the notice, including any personal note. */
  dismissNotice(churchId: string, noticeId: string, personId: string): Observable<void> {
    if (environment.demo) return this.demo.dismissNotice(churchId, noticeId, personId);
    return this.http.delete<void>(`${this.base}/churches/${churchId}/notices/${noticeId}`, {
      params: { person_id: personId },
    });
  }

  /** Draft the coming week's reminders (pending until a leader approves). */
  draftReminders(churchId: string, ministryId: string): Observable<unknown> {
    if (environment.demo) return this.demo.draftReminders(churchId, ministryId);
    return this.http.post(`${this.base}/churches/${churchId}/ministries/${ministryId}/reminders/draft`, {});
  }

  /** Ask Shepherd: a greeting and suggested questions from this week's data. */
  askStart(churchId: string, ministryId: string, personId: string): Observable<AskStart> {
    if (environment.demo) return this.demo.askStart(churchId, ministryId, personId);
    return this.http.get<AskStart>(`${this.base}/churches/${churchId}/ministries/${ministryId}/ask`, {
      params: { person_id: personId },
    });
  }

  /** One question (typed, or a tapped suggestion). Read-only: drafts come back to read. */
  ask(churchId: string, ministryId: string, body: AskIn): Observable<AskAnswer> {
    if (environment.demo) return this.demo.ask(churchId, ministryId, body);
    return this.http.post<AskAnswer>(`${this.base}/churches/${churchId}/ministries/${ministryId}/ask`, body);
  }

  /** Send drafts the leader read (and maybe edited): the tap is their approval. 1:1 only. */
  sendDrafts(churchId: string, ministryId: string, personId: string, drafts: AskDraft[]): Observable<AskSendOut> {
    if (environment.demo) return this.demo.sendDrafts(churchId, ministryId, personId, drafts);
    return this.http.post<AskSendOut>(`${this.base}/churches/${churchId}/ministries/${ministryId}/ask/send`, {
      person_id: personId,
      drafts: drafts.map(({ to_person_id, kind, body, gathering_id, role_id, assignment_id, replaces_assignment_id }) => ({
        to_person_id, kind, body, gathering_id, role_id, assignment_id, replaces_assignment_id,
      })),
    });
  }

  /** "Put … in" on a notice: someone said yes when asked (a swap if it was someone's place). */
  putIn(churchId: string, noticeId: string, personId: string): Observable<PutInOut> {
    if (environment.demo) return this.demo.putIn(churchId, noticeId, personId);
    return this.http.post<PutInOut>(`${this.base}/churches/${churchId}/notices/${noticeId}/put-in`, { person_id: personId });
  }

  /** Resolve: accept Shepherd's replacement on the leader's own roster. Messages no one. */
  acceptReplacement(churchId: string, huddleId: string, personId: string, ministryId: string): Observable<Huddle> {
    if (environment.demo) return this.demo.acceptReplacement(churchId, huddleId, personId, ministryId);
    return this.http.post<Huddle>(`${this.base}/churches/${churchId}/huddles/${huddleId}/accept-replacement`, {
      person_id: personId,
      ministry_id: ministryId,
    });
  }

  undoReplacement(churchId: string, huddleId: string, personId: string): Observable<Huddle> {
    if (environment.demo) return this.demo.undoReplacement(churchId, huddleId, personId);
    return this.http.post<Huddle>(`${this.base}/churches/${churchId}/huddles/${huddleId}/undo-replacement`, {
      person_id: personId,
    });
  }

  resolveHuddle(churchId: string, huddleId: string, personId: string, outcome: string): Observable<Huddle> {
    if (environment.demo) return this.demo.resolveHuddle(churchId, huddleId, personId, outcome);
    return this.http.post<Huddle>(`${this.base}/churches/${churchId}/huddles/${huddleId}/resolve`, {
      person_id: personId,
      outcome,
    });
  }

  memory(churchId: string, ministryId: string): Observable<Memory> {
    if (environment.demo) return this.demo.memory(churchId, ministryId);
    return this.http.get<Memory>(`${this.base}/churches/${churchId}/ministries/${ministryId}/memory`);
  }

  noteMemory(churchId: string, ministryId: string, personId: string, text: string): Observable<MemoryPending> {
    if (environment.demo) return this.demo.noteMemory(churchId, ministryId, personId, text);
    return this.http.post<MemoryPending>(`${this.base}/churches/${churchId}/ministries/${ministryId}/memory/notes`, {
      person_id: personId,
      text,
    });
  }

  deleteMemory(churchId: string, ministryId: string, memoryId: string, personId: string): Observable<void> {
    if (environment.demo) return this.demo.deleteMemory(churchId, ministryId, memoryId, personId);
    return this.http.delete<void>(`${this.base}/churches/${churchId}/ministries/${ministryId}/memory/${memoryId}`, {
      params: { person_id: personId },
    });
  }
}
