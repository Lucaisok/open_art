import { postFiles, requestJson } from "./api";
import type { ImageInfo } from "./types";

// Where an image of a project is served (api/images.py): only to its owner, so plain <img> tags work
export const imageUrl = (id: string) => `/api/images/${id}`;
export const thumbUrl = (id: string) => `/api/images/${id}/thumb`;

export const IMAGE_TYPES = "image/jpeg,image/png,image/webp,image/gif";

// Adds images to a saved project, one file per request: each request stays under the server's 10 MB
// limit. Stops at the first refusal and returns its sentence ("notes.txt: this file isn't an image…").
export const addImages = async (projectId: string, files: File[]): Promise<string | null> => {
    for (const file of files) {
        const result = await postFiles<ImageInfo[]>(`/api/projects/${projectId}/images`, "files", [file]);
        if (!result.ok) {
            return result.error;
        }
    }
    return null;
};

export const removeImage = async (projectId: string, imageId: string): Promise<string | null> => {
    const result = await requestJson("DELETE", `/api/projects/${projectId}/images/${imageId}`);
    return result.ok ? null : result.error;
};
