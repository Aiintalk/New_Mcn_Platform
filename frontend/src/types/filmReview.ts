export type FilmVideoRole = 'original' | 'edited';

export type FilmVideoStatus = 'selected' | 'uploading' | 'analyzing' | 'completed' | 'failed';

export interface SaveFilmReportRequest {
  task_id: number;
  report: string;
  original_filename: string;
  edited_filename: string;
}
