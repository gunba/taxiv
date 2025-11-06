import type {HierarchyNode, TaxDataObject} from '../types';

/**
 * Normalized shape accepted by the node formatting helper. This matches the fields
 * that Markdown generation depends on and can be satisfied by a `TaxDataObject`
 * (detail payload) or a `HierarchyNode` (navigation payload).
 */
export interface NodeFormattingInput {
	type?: string | null;
	title?: string | null;
	local_id?: string | null;
	ref_id?: string | null;
	act_id?: string | null;
}

export type NodeFormattingSource =
	| Pick<TaxDataObject, 'type' | 'title' | 'local_id' | 'ref_id' | 'act_id'>
	| (HierarchyNode & { local_id?: string | null; act_id?: string | null });

/**
 * Result returned from the node formatting helper. Consumers receive:
 *  - an ordered list of label variants (first entry is the preferred label), and
 *  - the recommended Markdown heading text (with graceful fallbacks when metadata
 *    is incomplete).
 */
export interface NodeFormattingResult {
	/** Preferred structural label for headings (first element of `orderedLabelVariants`). */
	preferredHeadingLabel: string;
	/** Ordered structural label variants (abbreviations, lowercase forms, etc.). */
	orderedLabelVariants: string[];
	/** Suggested Markdown heading text that merges the label with the descriptive title. */
	markdownHeading: string;
}

const IDENTIFIER_REGEX = /([0-9]+[A-Z]*-[0-9A-Z]+|[0-9]+[A-Z]*|[IVXLCDM]+)/i;

type NormalizedKind =
	| 'act'
	| 'chapter'
	| 'part'
	| 'division'
	| 'subdivision'
	| 'section'
	| 'schedule'
	| 'schedule_part'
	| 'schedule_division'
	| 'schedule_subdivision'
	| 'schedule_section'
	| 'guide'
	| 'operative'
	| 'definition'
	| 'unknown';

type ScheduleInfo = {
	id: string | null;
	subKind: 'part' | 'division' | 'subdivision' | 'section' | null;
};

interface ParsedType {
	kind: NormalizedKind;
	schedule: ScheduleInfo;
}

const DEFAULT_RESULT: NodeFormattingResult = {
	preferredHeadingLabel: 'Provision',
	orderedLabelVariants: ['Provision'],
	markdownHeading: 'Provision',
};

function coerceInput(node: NodeFormattingSource | NodeFormattingInput): NodeFormattingInput {
	return {
		type: node.type ?? null,
		title: node.title ?? null,
		local_id: 'local_id' in node ? (node as any).local_id ?? null : null,
		ref_id: node.ref_id ?? null,
		act_id: 'act_id' in node ? (node as any).act_id ?? null : null,
	};
}

function extractFromRef(refId: string | null | undefined): string | null {
	if (!refId) return null;
	const colonParts = refId.split(':');
	const lastColonPart = colonParts[colonParts.length - 1];
	if (lastColonPart && IDENTIFIER_REGEX.test(lastColonPart)) {
		return lastColonPart.trim();
	}
	const dashMatch = refId.match(IDENTIFIER_REGEX);
	return dashMatch ? dashMatch[1].trim() : null;
}

function extractFromTitle(title: string | null | undefined): string | null {
	if (!title) return null;
	const match = title.match(IDENTIFIER_REGEX);
	return match ? match[1].trim() : null;
}

function parseType(rawType: string | null | undefined): ParsedType {
	if (!rawType) {
		return {kind: 'unknown', schedule: {id: null, subKind: null}};
	}
	const normalized = rawType.trim();
	if (!normalized) {
		return {kind: 'unknown', schedule: {id: null, subKind: null}};
	}
	const segments = normalized.split(':').map(segment => segment.trim()).filter(Boolean);
	const base = (segments[0] ?? '').toLowerCase();
	if (base === 'schedule') {
		const scheduleId = segments.length > 1 ? segments[1] : null;
		const rawSub = segments.length > 2 ? segments[segments.length - 1].toLowerCase() : null;
		let subKind: ScheduleInfo['subKind'] = null;
		switch (rawSub) {
			case 'part':
				subKind = 'part';
				break;
			case 'division':
				subKind = 'division';
				break;
			case 'subdivision':
				subKind = 'subdivision';
				break;
			case 'section':
				subKind = 'section';
				break;
		}
		let kind: NormalizedKind = 'schedule';
		if (subKind) {
			if (subKind === 'part') kind = 'schedule_part';
			else if (subKind === 'division') kind = 'schedule_division';
			else if (subKind === 'subdivision') kind = 'schedule_subdivision';
			else if (subKind === 'section') kind = 'schedule_section';
		}
		return {kind, schedule: {id: scheduleId ?? null, subKind}};
	}
	switch (base) {
		case 'act':
			return {kind: 'act', schedule: {id: null, subKind: null}};
		case 'chapter':
			return {kind: 'chapter', schedule: {id: null, subKind: null}};
		case 'part':
			return {kind: 'part', schedule: {id: null, subKind: null}};
		case 'division':
			return {kind: 'division', schedule: {id: null, subKind: null}};
		case 'subdivision':
			return {kind: 'subdivision', schedule: {id: null, subKind: null}};
		case 'section':
			return {kind: 'section', schedule: {id: null, subKind: null}};
		case 'guide':
			return {kind: 'guide', schedule: {id: null, subKind: null}};
		case 'operativeprovision':
			return {kind: 'operative', schedule: {id: null, subKind: null}};
		case 'definition':
			return {kind: 'definition', schedule: {id: null, subKind: null}};
		default:
			return {kind: 'unknown', schedule: {id: null, subKind: null}};
	}
}

function uniquePush(list: string[], candidate: string | null | undefined): void {
	if (!candidate) return;
	const value = candidate.trim();
	if (!value) return;
	if (!list.includes(value)) {
		list.push(value);
	}
}

function buildStructuralVariants(base: string, id: string | null, abbreviations: string[] = []): {label: string; variants: string[]} {
	const trimmedId = id?.trim() ?? '';
	const label = trimmedId ? `${base} ${trimmedId}` : base;
	const variants: string[] = [];
	uniquePush(variants, label);
	uniquePush(variants, trimmedId ? `${base.toLowerCase()} ${trimmedId}` : base.toLowerCase());
	if (trimmedId) {
		for (const abbr of abbreviations) {
			const trimmedAbbr = abbr.trim();
			if (!trimmedAbbr) continue;
			uniquePush(variants, `${trimmedAbbr} ${trimmedId}`);
			uniquePush(variants, `${trimmedAbbr.toLowerCase()} ${trimmedId}`);
		}
	}
	return {label, variants};
}

function buildScheduleVariants(schedule: ScheduleInfo, id: string | null): {label: string; variants: string[]} {
	const scheduleId = schedule.id?.trim() ?? '';
	const scheduleLabel = scheduleId ? `Schedule ${scheduleId}` : 'Schedule';
	const scheduleLower = scheduleLabel.toLowerCase();
	const scheduleAbbr = scheduleId ? `Sch ${scheduleId}` : 'Sch';
	const variants: string[] = [];
	if (!schedule.subKind) {
		uniquePush(variants, scheduleLabel);
		uniquePush(variants, scheduleLower);
		uniquePush(variants, scheduleAbbr);
		uniquePush(variants, scheduleAbbr.toLowerCase());
		return {label: scheduleLabel, variants};
	}

	const trimmedId = id?.trim() ?? '';
	const subKind = schedule.subKind;
	const subMapping: Record<typeof subKind, {display: string; abbreviations: string[]}> = {
		part: {display: 'Part', abbreviations: ['Pt']},
		division: {display: 'Division', abbreviations: ['Div']},
		subdivision: {display: 'Subdivision', abbreviations: ['Subdiv']},
		section: {display: 'Section', abbreviations: ['Sect', 's']},
	};
	const mapping = subMapping[subKind];
	const display = mapping.display;
	const lowerDisplay = display.toLowerCase();
	const label = trimmedId ? `${scheduleLabel} ${display} ${trimmedId}` : `${scheduleLabel} ${display}`;
	uniquePush(variants, label);
	uniquePush(variants, trimmedId ? `${scheduleLower} ${lowerDisplay} ${trimmedId}` : `${scheduleLower} ${lowerDisplay}`);
	for (const abbr of mapping.abbreviations) {
		uniquePush(variants, trimmedId ? `${scheduleLabel} ${abbr} ${trimmedId}` : `${scheduleLabel} ${abbr}`);
		uniquePush(variants, trimmedId ? `${scheduleAbbr} ${abbr} ${trimmedId}` : `${scheduleAbbr} ${abbr}`);
		uniquePush(variants, trimmedId ? `${scheduleAbbr.toLowerCase()} ${abbr.toLowerCase()} ${trimmedId}` : `${scheduleAbbr.toLowerCase()} ${abbr.toLowerCase()}`);
	}
	uniquePush(variants, scheduleLabel);
	uniquePush(variants, scheduleLower);
	uniquePush(variants, scheduleAbbr);
	uniquePush(variants, scheduleAbbr.toLowerCase());
	return {label, variants};
}

function buildMarkdownHeading(preferredLabel: string, title: string | null | undefined): string {
	const trimmedLabel = preferredLabel.trim();
	const trimmedTitle = (title ?? '').trim();
	if (!trimmedTitle && trimmedLabel) {
		return trimmedLabel;
	}
	if (!trimmedLabel && trimmedTitle) {
		return trimmedTitle;
	}
	if (!trimmedLabel && !trimmedTitle) {
		return DEFAULT_RESULT.markdownHeading;
	}
	if (trimmedTitle.toLowerCase().startsWith(trimmedLabel.toLowerCase())) {
		return trimmedTitle;
	}
	return `${trimmedLabel} — ${trimmedTitle}`;
}

/**
 * Generate ordered structural label variants and a recommended Markdown heading label
 * for provision-like nodes. This helper centralizes the formatting rules for sections,
 * parts, divisions, schedules, and fallback types so downstream features (markdown
 * export, search snippets, future case-law integrations) can share consistent labels.
 */
export function formatNodeHeading(node: NodeFormattingSource | NodeFormattingInput): NodeFormattingResult {
	const coerced = coerceInput(node);
	const rawTitle = coerced.title?.trim() ?? '';
	const parsedType = parseType(coerced.type ?? null);
	const inferredId = coerced.local_id?.trim() || extractFromRef(coerced.ref_id) || extractFromTitle(rawTitle);
	const variants: string[] = [];
	let preferredLabel: string | null = null;

	switch (parsedType.kind) {
		case 'act': {
			const label = rawTitle || 'Act';
			preferredLabel = label;
			uniquePush(variants, label);
			if (label !== 'Act') {
				uniquePush(variants, 'Act');
			}
			break;
		}
		case 'chapter': {
			const {label, variants: generated} = buildStructuralVariants('Chapter', inferredId, ['Ch']);
			preferredLabel = label;
			generated.forEach(value => uniquePush(variants, value));
			break;
		}
		case 'part': {
			const {label, variants: generated} = buildStructuralVariants('Part', inferredId, ['Pt']);
			preferredLabel = label;
			generated.forEach(value => uniquePush(variants, value));
			break;
		}
		case 'division': {
			const {label, variants: generated} = buildStructuralVariants('Division', inferredId, ['Div']);
			preferredLabel = label;
			generated.forEach(value => uniquePush(variants, value));
			break;
		}
		case 'subdivision': {
			const {label, variants: generated} = buildStructuralVariants('Subdivision', inferredId, ['Subdiv']);
			preferredLabel = label;
			generated.forEach(value => uniquePush(variants, value));
			break;
		}
		case 'section': {
			const {label, variants: generated} = buildStructuralVariants('Section', inferredId, ['Sect', 's']);
			preferredLabel = label;
			generated.forEach(value => uniquePush(variants, value));
			break;
		}
		case 'schedule':
		case 'schedule_part':
		case 'schedule_division':
		case 'schedule_subdivision':
		case 'schedule_section': {
			const {label, variants: generated} = buildScheduleVariants(parsedType.schedule, inferredId);
			preferredLabel = label;
			generated.forEach(value => uniquePush(variants, value));
			break;
		}
		case 'guide':
		case 'operative':
		case 'definition':
		case 'unknown':
		default: {
			preferredLabel = rawTitle || inferredId || coerced.ref_id || DEFAULT_RESULT.preferredHeadingLabel;
			uniquePush(variants, preferredLabel);
			break;
		}
	}

	if (!variants.length) {
		return DEFAULT_RESULT;
	}

	if (!preferredLabel) {
		preferredLabel = variants[0];
	}

	if (coerced.ref_id) {
		uniquePush(variants, coerced.ref_id);
	}

	const markdownHeading = buildMarkdownHeading(preferredLabel, rawTitle || null);

	return {
		preferredHeadingLabel: preferredLabel,
		orderedLabelVariants: variants,
		markdownHeading,
	};
}

