import React from 'react';
import type {ActInfo} from '../types';

interface ActSelectorProps {
	acts: ActInfo[];
	value: string | null;
	onChange: (actId: string) => void;
}

const ActSelector: React.FC<ActSelectorProps> = ({acts, value, onChange}) => {
	if (acts.length <= 1) {
		return null;
	}

	return (
		<label className="flex items-center gap-2 text-sm text-gray-300">
			<select
				aria-label="Act"
				className="bg-gray-800 border border-gray-600 rounded-md px-3 py-1 text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-400"
				value={value ?? ''}
				onChange={event => onChange(event.target.value)}
			>
				{acts.map(act => (
					<option key={act.id} value={act.id}>
						{act.title}
					</option>
				))}
			</select>
		</label>
	);
};

export default ActSelector;
