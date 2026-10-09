import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';
import type {
  AskAnswer,
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
  private readonly base = environment.apiUrl;

  churches(): Observable<Church[]> {
    return this.http.get<Church[]>(`${this.base}/churches`);
  }

  leaders(churchId: string): Observable<Leader[]> {
    return this.http.get<Leader[]>(`${this.base}/churches/${churchId}/leaders`);
  }

  ministries(churchId: string): Observable<Ministry[]> {
    return this.http.get<Ministry[]>(`${this.base}/churches/${churchId}/ministries`);
  }

  briefing(churchId: string, personId: string): Observable<Briefing> {
    return this.http.get<Briefing>(`${this.base}/churches/${churchId}/leaders/${personId}/briefing`);
  }

  roster(churchId: string, ministryId: string, start?: string, end?: string): Observable<Roster> {
    const params: Record<string, string> = {};
    if (start) params['start'] = start;
    if (end) params['end'] = end;
    return this.http.get<Roster>(`${this.base}/churches/${churchId}/ministries/${ministryId}/roster`, { params });
  }

  suggestion(churchId: string, ministryId: string): Observable<Suggestion> {
    return this.http.get<Suggestion>(`${this.base}/churches/${churchId}/ministries/${ministryId}/suggestion`);
  }

  approveSuggestion(
    churchId: string,
    ministryId: string,
    personId: string,
    assignments: SuggestedAssignment[],
  ): Observable<Proposal> {
    return this.http.post<Proposal>(`${this.base}/churches/${churchId}/ministries/${ministryId}/suggestion/approve`, {
      person_id: personId,
      assignments,
    });
  }

  pendingProposals(churchId: string): Observable<Proposal[]> {
    return this.http.get<Proposal[]>(`${this.base}/churches/${churchId}/proposals`, {
      params: { status: 'pending' },
    });
  }

  approve(churchId: string, proposalId: string, personId: string): Observable<Proposal> {
    return this.http.post<Proposal>(`${this.base}/churches/${churchId}/proposals/${proposalId}/approve`, {
      person_id: personId,
    });
  }

  reject(churchId: string, proposalId: string, personId: string): Observable<Proposal> {
    return this.http.post<Proposal>(`${this.base}/churches/${churchId}/proposals/${proposalId}/reject`, {
      person_id: personId,
    });
  }

  startHuddle(churchId: string, findingId: string, personId: string): Observable<Huddle> {
    return this.http.post<Huddle>(`${this.base}/churches/${churchId}/findings/${findingId}/huddle`, {
      person_id: personId,
    });
  }

  chooseSlot(churchId: string, huddleId: string, personId: string, slotId: string): Observable<Huddle> {
    return this.http.post<Huddle>(`${this.base}/churches/${churchId}/huddles/${huddleId}/choose`, {
      person_id: personId,
      slot_id: slotId,
    });
  }

  /** Ask Shepherd: a greeting and suggested questions from this week's data. */
  askStart(churchId: string, ministryId: string, personId: string): Observable<AskStart> {
    return this.http.get<AskStart>(`${this.base}/churches/${churchId}/ministries/${ministryId}/ask`, {
      params: { person_id: personId },
    });
  }

  /** One question (typed, or a tapped suggestion). Read-only: drafts come back to copy. */
  ask(churchId: string, ministryId: string, body: AskIn): Observable<AskAnswer> {
    return this.http.post<AskAnswer>(`${this.base}/churches/${churchId}/ministries/${ministryId}/ask`, body);
  }

  /** Resolve: accept Shepherd's replacement on the leader's own roster. Messages no one. */
  acceptReplacement(churchId: string, huddleId: string, personId: string, ministryId: string): Observable<Huddle> {
    return this.http.post<Huddle>(`${this.base}/churches/${churchId}/huddles/${huddleId}/accept-replacement`, {
      person_id: personId,
      ministry_id: ministryId,
    });
  }

  undoReplacement(churchId: string, huddleId: string, personId: string): Observable<Huddle> {
    return this.http.post<Huddle>(`${this.base}/churches/${churchId}/huddles/${huddleId}/undo-replacement`, {
      person_id: personId,
    });
  }

  resolveHuddle(churchId: string, huddleId: string, personId: string, outcome: string): Observable<Huddle> {
    return this.http.post<Huddle>(`${this.base}/churches/${churchId}/huddles/${huddleId}/resolve`, {
      person_id: personId,
      outcome,
    });
  }

  memory(churchId: string, ministryId: string): Observable<Memory> {
    return this.http.get<Memory>(`${this.base}/churches/${churchId}/ministries/${ministryId}/memory`);
  }

  noteMemory(churchId: string, ministryId: string, personId: string, text: string): Observable<MemoryPending> {
    return this.http.post<MemoryPending>(`${this.base}/churches/${churchId}/ministries/${ministryId}/memory/notes`, {
      person_id: personId,
      text,
    });
  }

  deleteMemory(churchId: string, ministryId: string, memoryId: string, personId: string): Observable<void> {
    return this.http.delete<void>(`${this.base}/churches/${churchId}/ministries/${ministryId}/memory/${memoryId}`, {
      params: { person_id: personId },
    });
  }
}
