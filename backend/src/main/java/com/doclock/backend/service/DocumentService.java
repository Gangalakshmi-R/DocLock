package com.doclock.backend.service;

import com.doclock.backend.entity.Document;
import com.doclock.backend.entity.DocumentChunk;
import com.doclock.backend.entity.DocumentContent;
import com.doclock.backend.entity.DocumentStatus;
import com.doclock.backend.repository.DocumentFactRepository;
import com.doclock.backend.repository.DocumentAlertRepository;
import com.doclock.backend.repository.DocumentChunkRepository;
import com.doclock.backend.repository.DocumentContentRepository;
import com.doclock.backend.repository.DocumentRepository;
import org.apache.tika.Tika;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.web.multipart.MultipartFile;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardCopyOption;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.NoSuchElementException;
import java.util.Objects;
import java.util.UUID;

@Service
public class DocumentService {
    private static final long MAX_FILE_SIZE = 50L * 1024 * 1024;
    private static final List<String> ALLOWED_EXTENSIONS = List.of(
            ".pdf", ".doc", ".docx", ".txt", ".rtf", ".ppt", ".pptx",
            ".xls", ".xlsx", ".csv", ".html", ".htm", ".xml", ".odt",
            ".ods", ".odp", ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff"
    );

    private final DocumentRepository documents;
    private final DocumentContentRepository contents;
    private final DocumentChunkRepository chunks;
    private final DocumentFactRepository facts;
    private final DocumentAlertRepository alerts;
    private final EmbeddingService embeddings;
    private final ChromaService chroma;
    private final Tika tika = new Tika();

    @Value("${doclock.storage.dir}")
    private String storageDirectory;

    public DocumentService(DocumentRepository documents,
                           DocumentContentRepository contents,
                           DocumentChunkRepository chunks,
                           DocumentFactRepository facts,
                           DocumentAlertRepository alerts,
                           EmbeddingService embeddings,
                           ChromaService chroma) {
        this.documents = documents;
        this.contents = contents;
        this.chunks = chunks;
        this.facts = facts;
        this.alerts = alerts;
        this.embeddings = embeddings;
        this.chroma = chroma;
    }

    /** Saves the original file, extracts its text, creates chunks and stores embeddings. */
    @Transactional
    public Document upload(MultipartFile file) throws Exception {
        if (file == null || file.isEmpty()) {
            throw new IllegalArgumentException("Please select a non-empty file.");
        }
        if (file.getSize() > MAX_FILE_SIZE) {
            throw new IllegalArgumentException("File is too large. Maximum size is 50 MB.");
        }

        String originalName = Paths.get(Objects.requireNonNullElse(
                file.getOriginalFilename(), "document")).getFileName().toString();
        String lowerName = originalName.toLowerCase(Locale.ROOT);
        boolean allowed = ALLOWED_EXTENSIONS.stream().anyMatch(lowerName::endsWith);
        if (!allowed) {
            throw new IllegalArgumentException("Unsupported file type. Upload PDF, Office, text or image files.");
        }
        if (originalName.length() > 250) {
            throw new IllegalArgumentException("Filename is too long.");
        }

        Path root = Paths.get(storageDirectory).toAbsolutePath().normalize();
        Files.createDirectories(root);
        String safeName = UUID.randomUUID() + "_" + originalName.replaceAll("[^a-zA-Z0-9._-]", "_");
        Path savedFile = root.resolve(safeName).normalize();
        if (!savedFile.startsWith(root)) {
            throw new IllegalArgumentException("Invalid filename.");
        }

        try (var input = file.getInputStream()) {
            Files.copy(input, savedFile, StandardCopyOption.REPLACE_EXISTING);
        }

        Document document = Document.builder()
                .filename(safeName)
                .originalFilename(originalName)
                .contentType(Objects.requireNonNullElse(file.getContentType(), "application/octet-stream"))
                .size(file.getSize())
                .storagePath(savedFile.toString())
                .status(DocumentStatus.PROCESSING)
                .uploadedAt(LocalDateTime.now())
                .build();
        document = documents.save(document);

        try {
            String extractedText;
            try (var input = Files.newInputStream(savedFile)) {
                extractedText = tika.parseToString(input);
            }
            if (extractedText == null) extractedText = "";

            contents.save(DocumentContent.builder()
                    .document(document)
                    .extractedText(extractedText)
                    .wordCount(extractedText.isBlank() ? 0 : extractedText.trim().split("\\s+").length)
                    .build());

            List<String> textChunks = splitIntoChunks(extractedText, 1000, 150);
            for (int index = 0; index < textChunks.size(); index++) {
                String chunkText = textChunks.get(index);
                List<Double> vector = embeddings.embed(chunkText);
                String vectorJson = vector.isEmpty() ? null : vector.toString();

                String vectorId = "doc-" + document.getId() + "-chunk-" + index;
                DocumentChunk chunk = chunks.save(DocumentChunk.builder()
                        .document(document)
                        .chunkIndex(index)
                        .content(chunkText)
                        .vectorId(vectorId)
                        .vectorJson(vectorJson)
                        .startChar(0)
                        .endChar(chunkText.length())
                        .build());

                if (!vector.isEmpty()) {
                    chroma.upsert(vectorId, vector, chunkText, document.getId(), originalName, index);
                }
            }

            document.setStatus(DocumentStatus.PROCESSED);
            document.setProcessedAt(LocalDateTime.now());
            if (textChunks.isEmpty()) {
                document.setErrorMessage("No readable text was extracted. The original file is still available to view/download.");
            }
        } catch (Exception exception) {
            // Do not leave half-created passages or vectors behind after an indexing failure.
            List<String> savedVectorIds = chunks.findByDocumentIdOrderByChunkIndex(document.getId()).stream()
                    .map(DocumentChunk::getVectorId).filter(Objects::nonNull).toList();
            chroma.delete(savedVectorIds);
            chunks.deleteByDocumentId(document.getId());
            contents.deleteByDocumentId(document.getId());
            document.setStatus(DocumentStatus.FAILED);
            document.setErrorMessage(exception.getMessage() == null ? "Document processing failed." : exception.getMessage());
        }

        return documents.save(document);
    }

    private List<String> splitIntoChunks(String text, int chunkSize, int overlap) {
        List<String> result = new ArrayList<>();
        if (text == null || text.isBlank()) return result;

        int start = 0;
        while (start < text.length()) {
            int end = Math.min(text.length(), start + chunkSize);
            if (end < text.length()) {
                int space = text.lastIndexOf(' ', end);
                if (space > start + chunkSize / 2) end = space;
            }
            String chunk = text.substring(start, end).trim();
            if (!chunk.isEmpty()) result.add(chunk);
            if (end >= text.length()) break;
            start = Math.max(start + 1, end - overlap);
        }
        return result;
    }

    public List<Document> list(String search) {
        if (search == null || search.isBlank()) return documents.findAllByOrderByUploadedAtDesc();
        return documents.findByOriginalFilenameContainingIgnoreCaseOrderByUploadedAtDesc(search);
    }

    public Document get(Long id) {
        return documents.findById(id)
                .orElseThrow(() -> new NoSuchElementException("Document not found."));
    }

    public Path path(Long id) {
        Path file = Paths.get(get(id).getStoragePath()).toAbsolutePath().normalize();
        if (!Files.exists(file)) throw new NoSuchElementException("The stored document file is missing.");
        return file;
    }

    @Transactional
    public void delete(Long id) {
        Document document = get(id);
        Path storedFile = Paths.get(document.getStoragePath());

        // Remove vectors and dependent rows before deleting the document record.
        List<String> vectorIds = chunks.findByDocumentIdOrderByChunkIndex(id).stream()
                .map(DocumentChunk::getVectorId).filter(Objects::nonNull).toList();
        chroma.delete(vectorIds);
        chunks.deleteByDocumentId(id);
        contents.deleteByDocumentId(id);
        facts.deleteByDocumentId(id);
        alerts.deleteByDocumentId(id);
        documents.delete(document);

        // Delete the physical file only after the database transaction commits.
        TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
            @Override
            public void afterCommit() {
                try {
                    Files.deleteIfExists(storedFile);
                } catch (Exception ignored) {
                    // The database record is already gone; a leftover file can be cleaned manually.
                }
            }
        });
    }

    public String text(Long id) {
        get(id); // Return 404 for an unknown document ID.
        return contents.findByDocumentId(id)
                .map(DocumentContent::getExtractedText)
                .orElse("");
    }
}
