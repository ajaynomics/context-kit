const MAX_LINKS = 500;
const MAX_IMAGES = 200;
const MAX_VIDEO = 50;
const MAX_AUDIO = 50;
const MAX_ATTACHMENTS = 10;

export function boundFetchCollections(result) {
  const warnings = [...(result.warnings || [])];
  const trim = (value, maximum, label) => {
    if (!Array.isArray(value)) return value;
    if (value.length > maximum) warnings.push(`${label} truncated from ${value.length} to ${maximum}`);
    return value.slice(0, maximum);
  };
  if (result.links) result.links = trim(result.links, MAX_LINKS, "links");
  if (result.media) {
    result.media.images = trim(result.media.images, MAX_IMAGES, "images");
    result.media.videos = trim(result.media.videos, MAX_VIDEO, "videos");
    result.media.audio = trim(result.media.audio, MAX_AUDIO, "audio");
  }
  if (result.attachments) result.attachments = trim(result.attachments, MAX_ATTACHMENTS, "attachments");
  result.warnings = warnings;
  return result;
}
