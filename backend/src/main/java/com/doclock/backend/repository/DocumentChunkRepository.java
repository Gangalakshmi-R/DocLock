package com.doclock.backend.repository;
import com.doclock.backend.entity.*; import org.springframework.data.jpa.repository.JpaRepository; import java.util.List;
public interface DocumentChunkRepository extends JpaRepository<DocumentChunk,Long>{ List<DocumentChunk> findByDocumentIdOrderByChunkIndex(Long id); void deleteByDocumentId(Long id); List<DocumentChunk> findByVectorIdIn(List<String> ids); List<DocumentChunk> findAllByOrderByIdAsc(); }
