package com.doclock.backend.repository;
import com.doclock.backend.entity.*; import org.springframework.data.jpa.repository.JpaRepository; import java.util.Optional;
public interface DocumentContentRepository extends JpaRepository<DocumentContent,Long>{ Optional<DocumentContent> findByDocumentId(Long id); void deleteByDocumentId(Long id); }
